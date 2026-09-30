"""Pipeline stages. Each one is idempotent and can be re-run on its own.

A stage records the hash of the inputs it ran against. If those inputs change
later, stage_status() reports the stage as stale.
"""

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Callable

from . import align, captions, config, ff, store
from .models import Project, SectionAudio
from .timeline import Piece, build_timeline

Progress = Callable[[float, str], None]

RENDER_VERSION = 1  # bump to invalidate cached pieces after changing encode settings


# ------------------------------------------------------------------ hashes

def captions_hash(p: Project) -> str:
    return store.hash_json({
        "narration": p.narration.sha if p.narration else None,
        "text": [s.text for s in p.sections],
        "model": config.WHISPER_MODEL, "mode": config.WHISPER_MODE,
    })


def assemble_hash(p: Project) -> str:
    return store.hash_json({
        "timeline": build_timeline(p).to_dict(),
        "captions": p.stages.get("captions").input_hash if "captions" in p.stages else None,
        "narration": p.narration.sha if p.narration else None,
        "music": p.music.model_dump(), "styles": p.styles.model_dump(),
        "formats": p.formats, "v": RENDER_VERSION,
    })


STAGE_HASHES = {"captions": captions_hash, "assemble": assemble_hash}


def stage_status(p: Project) -> dict[str, str]:
    out = {}
    for name, fn in STAGE_HASHES.items():
        st = p.stages.get(name)
        if not st:
            out[name] = "pending"
            continue
        try:
            out[name] = "done" if st.input_hash == fn(p) else "stale"
        except ValueError:
            out[name] = "stale"
    return out


# ------------------------------------------------------------------ narration

def import_narration(pid: str, upload: Path) -> None:
    """Normalise an uploaded recording to 48 kHz WAV and record its duration."""
    d = store.project_dir(pid)
    out = d / "audio" / "narration.wav"
    ff.run(["-i", str(upload), "-vn", "-ac", "2", "-ar", "48000", "-c:a", "pcm_s16le", str(out)])
    info = ff.probe(out)
    sha = store.file_sha(out)

    def fn(p: Project):
        from .models import Narration
        p.narration = Narration(file="audio/narration.wav", duration=round(info["duration"], 3), sha=sha)
        # A new recording invalidates old section timings.
        for s in p.sections:
            s.audio = None

    store.update(pid, fn)


# ------------------------------------------------------------------ footage

def make_proxy(pid: str, filename: str, progress: Progress) -> None:
    """Low-res H.264 copy for scrubbing in the browser (which can't play MKV/HEVC)."""
    d = store.project_dir(pid)
    src = store.safe_path(pid, f"footage/{filename}")
    info = ff.probe(src)
    out = d / "proxies" / f"{filename}.mp4"
    ff.run(
        ["-i", str(src), "-vf", "scale=-2:540", "-c:v", "libx264", "-preset", "veryfast",
         "-crf", "28", "-g", "15", "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", str(out)],
        duration=info["duration"], on_progress=lambda f: progress(f, "making preview copy"),
    )
    store.update(pid, lambda p: p.footage.__setitem__(filename, info))


# ------------------------------------------------------------------ captions

def run_captions(pid: str, progress: Progress) -> None:
    p = store.load(pid)
    if not p.narration:
        raise RuntimeError("Upload a narration recording first.")
    if not p.sections:
        raise RuntimeError("Add script sections first.")
    d = store.project_dir(pid)
    h = captions_hash(p)

    cache = d / "captions" / f"transcript-{p.narration.sha}-{config.WHISPER_MODEL}.json"
    if cache.exists():
        spoken = json.loads(cache.read_text(encoding="utf-8"))
    else:
        progress(0.05, f"transcribing with Whisper ({config.WHISPER_MODEL}) — this can take a few minutes")
        spoken = captions.transcribe(d / p.narration.file)
        cache.write_text(json.dumps(spoken), encoding="utf-8")

    progress(0.9, "aligning transcript to script")
    result = align.align([s.text for s in p.sections], spoken)
    (d / "captions" / "words.json").write_text(json.dumps(result.to_dict(), indent=1), encoding="utf-8")

    def fn(proj: Project):
        for s, start in zip(proj.sections, result.section_starts):
            if s.audio and s.audio.source == "manual":
                continue  # the user nudged this boundary; keep it
            s.audio = SectionAudio(start=start, source="aligned")

    store.update(pid, fn)
    store.mark_stage(pid, "captions", h, {
        "match_ratio": result.match_ratio,
        "skipped": result.skipped[:50], "extra": result.extra[:50],
        "warning": "Recording differs a lot from the script." if result.match_ratio < 0.6 else None,
    })


# ------------------------------------------------------------------ assemble

def _fit_filter(fmt: str, fill: str, crop_x: float, fps: int) -> str:
    w, h = config.FORMATS[fmt]
    tail = f"fps={fps},format=yuv420p,setsar=1"
    if fill == "blur":
        return (f"split[a][b];[a]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},"
                f"boxblur=30:2,eq=brightness=-0.08[bg];[b]scale={w}:{h}:force_original_aspect_ratio=decrease[fg];"
                f"[bg][fg]overlay=(W-w)/2:(H-h)/2,{tail}")
    return (f"scale={w}:{h}:force_original_aspect_ratio=increase,"
            f"crop={w}:{h}:(iw-{w})*{crop_x:.4f}:(ih-{h})/2,{tail}")


def _render_piece(pid: str, piece: Piece, fmt: str, fill: str, fps: int) -> Path:
    d = store.project_dir(pid)
    w, h = config.FORMATS[fmt]
    key = {"piece": piece.__dict__, "fmt": fmt, "fill": fill, "fps": fps, "v": RENDER_VERSION}
    if piece.source:
        src = store.safe_path(pid, f"footage/{piece.source}")
        key["src"] = [str(src), src.stat().st_mtime, src.stat().st_size]
    out = d / "cache" / f"{store.hash_json(key)}.mp4"
    if out.exists():
        return out

    enc = ["-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "16",
           "-frames:v", str(piece.frames), "-r", str(fps)]
    tmp = out.with_suffix(".part.mp4")
    if piece.source:
        # tpad clones the last frame if the source ends early, so frame counts stay exact.
        vf = _fit_filter(fmt, fill, piece.crop_x, fps) + ",tpad=stop_mode=clone:stop_duration=5"
        ff.run(["-ss", f"{piece.t_in:.3f}", "-i", str(src), "-filter_complex", vf, *enc, str(tmp)])
    else:
        ff.run(["-f", "lavfi", "-i", f"color=black:s={w}x{h}:r={fps}",
                "-vf", "format=yuv420p,setsar=1", *enc, str(tmp)])
    tmp.replace(out)
    return out


def _audio_graph(p: Project, has_music: bool) -> str:
    narr = "[1:a]aresample=48000,aformat=channel_layouts=stereo"
    if not has_music:
        return f"{narr},loudnorm=I=-14:TP=-1.5:LRA=11[a]"
    music = f"[2:a]aresample=48000,aformat=channel_layouts=stereo,volume={p.music.volume_db}dB"
    if p.music.duck:
        return (f"{narr},asplit=2[n][sc];{music}[m];"
                f"[m][sc]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=500[duck];"
                f"[n][duck]amix=inputs=2:duration=first:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=11[a]")
    return (f"{narr}[n];{music}[m];[n][m]amix=inputs=2:duration=first:normalize=0,"
            f"loudnorm=I=-14:TP=-1.5:LRA=11[a]")


def run_assemble(pid: str, progress: Progress) -> None:
    p = store.load(pid)
    if not p.sections:
        raise RuntimeError("Add script sections first.")
    tl = build_timeline(p)
    h = assemble_hash(p)
    d = store.project_dir(pid)
    fps, fill = tl.fps, p.styles.vertical_fill
    words_file = d / "captions" / "words.json"
    use_captions = p.styles.captions.enabled and p.narration and words_file.exists()
    words = captions.load_words(words_file) if use_captions else []
    music = config.MUSIC_DIR / p.music.file if p.music.file else None
    if music and not music.exists():
        raise RuntimeError(f"Music track {p.music.file} is missing from the music/ folder.")

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = d / "renders" / stamp
    out_dir.mkdir(parents=True)
    pieces = [pc for s in tl.sections for pc in s.pieces]
    n_steps = len(p.formats) * (len(pieces) + 1)
    step = 0
    outputs = {}
    used_pieces: set[Path] = set()

    for fmt in p.formats:
        w, hgt = config.FORMATS[fmt]
        # 16:9 output from 16:9 footage: crop and blur are equivalent; blur handles vertical sources.
        fmt_fill = fill if fmt == "vertical" else "blur"
        files = []
        for pc in pieces:
            progress(step / n_steps, f"{fmt}: cutting clips ({len(files) + 1}/{len(pieces)})")
            files.append(_render_piece(pid, pc, fmt, fmt_fill, fps))
            step += 1
        used_pieces.update(files)

        concat = out_dir / f"{fmt}-concat.txt"
        concat.write_text("".join(f"file '{f.as_posix()}'\n" for f in files), encoding="utf-8")
        video_only = out_dir / f"{fmt}-video.mp4"
        ff.run(["-f", "concat", "-safe", "0", "-i", str(concat), "-c", "copy", str(video_only)])

        inputs = ["-i", str(video_only)]
        if p.narration:
            inputs += ["-i", str(d / p.narration.file)]
        else:
            inputs += ["-f", "lavfi", "-t", f"{tl.duration:.3f}", "-i", "anullsrc=r=48000:cl=stereo"]
        if music:
            inputs += ["-stream_loop", "-1", "-i", str(music)]

        vf = "[0:v]null[v]"
        if words:
            ass_rel = f"captions/{fmt}.ass"
            (d / ass_rel).write_text(captions.build_ass(words, p.styles.captions, fmt, w, hgt), encoding="utf-8")
            # cwd is the project dir, so the .ass path stays relative (no Windows drive-colon escaping).
            vf = f"[0:v]subtitles={ass_rel}:fontsdir={ff.filter_path(config.FONTS_DIR)}[v]"

        final = out_dir / f"{fmt}.mp4"
        base_step = step
        ff.run(
            [*inputs, "-filter_complex", f"{vf};{_audio_graph(p, bool(music))}",
             "-map", "[v]", "-map", "[a]", "-t", f"{tl.duration:.3f}",
             "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-b:a", "192k", "-map_metadata", "-1", "-map_chapters", "-1",
             "-movflags", "+faststart", str(final)],
            cwd=d, duration=tl.duration,
            on_progress=lambda f: progress((base_step + f) / n_steps, f"{fmt}: encoding final video"),
        )
        step += 1
        video_only.unlink(missing_ok=True)
        concat.unlink(missing_ok=True)
        outputs[fmt] = f"renders/{stamp}/{fmt}.mp4"

    store.mark_stage(pid, "assemble", h, {"files": outputs, "warnings": tl.warnings,
                                          "estimated_timing": tl.estimated})
    cleanup_renders(pid, keep_cache=used_pieces)


# ------------------------------------------------------------------ cleanup

def cleanup_renders(pid: str, keep_cache: set[Path]) -> None:
    """Keep the newest KEEP_RENDERS renders; drop cached clip pieces the latest render didn't use."""
    d = store.project_dir(pid)
    renders = sorted((x for x in (d / "renders").iterdir() if x.is_dir()), reverse=True)
    for old in renders[config.KEEP_RENDERS:]:
        shutil.rmtree(old, ignore_errors=True)
    for f in (d / "cache").iterdir():
        if f not in keep_cache:
            f.unlink(missing_ok=True)
