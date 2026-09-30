"""End-to-end: generated footage + tone narration → rendered 9:16 and 16:9 files.

Whisper isn't run here: words.json is written directly, standing in for the
captions stage, so the test is fast and offline.
"""

import json
import shutil
import subprocess

import pytest

from app import config, ff, stages, store
from app.align import Alignment, Word
from app.models import Clip, Section, SectionAudio

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


def make_video(path, seconds, size="1280x720"):
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
                    f"testsrc2=s={size}:r=60:d={seconds}", "-c:v", "libx264", "-preset", "ultrafast",
                    str(path)], check=True)


def make_tone(path, seconds, freq=440):
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
                    f"sine=f={freq}:d={seconds}", str(path)], check=True)


def frame_count(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
                          "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True)
    return int(out.stdout.strip())


def test_assemble_both_formats(tmp_path):
    p = store.create("Render test")
    d = store.project_dir(p.id)
    make_video(d / "footage" / "game.mp4", 3)
    make_video(d / "footage" / "tall.mp4", 2, size="720x1280")
    make_tone(tmp_path / "voice.wav", 4.0)
    stages.import_narration(p.id, tmp_path / "voice.wav")
    make_tone(config.MUSIC_DIR / "bed.mp3", 1.5, freq=220)

    def setup(proj):
        proj.footage = {"game.mp4": ff.probe(d / "footage" / "game.mp4"),
                        "tall.mp4": ff.probe(d / "footage" / "tall.mp4")}
        proj.sections = [
            # 1.7 s of audio but only 1 s of footage → loops
            Section(id="s1", kind="hook", text="big claim here", audio=SectionAudio(start=0),
                    clips=[Clip(source="game.mp4", t_in=0.5, t_out=1.5, crop_x=0.2)]),
            Section(id="s2", text="the evidence", audio=SectionAudio(start=1.7),
                    clips=[Clip(source="tall.mp4", t_in=0, t_out=2)]),
            Section(id="s3", kind="cta", text="follow", audio=SectionAudio(start=3.2)),  # no clips
        ]
        proj.music.file = "bed.mp3"
        proj.styles.vertical_fill = "blur"

    store.update(p.id, setup)
    words = [Word("big", .1, .4, 0), Word("claim", .4, .8, 0), Word("here", .8, 1.2, 0),
             Word("the", 1.8, 2.0, 1), Word("evidence", 2.0, 2.8, 1), Word("follow", 3.3, 3.8, 2)]
    (d / "captions" / "words.json").write_text(
        json.dumps(Alignment(words, [0, 1.7, 3.2], 1.0, [], []).to_dict()))

    seen = []
    stages.run_assemble(p.id, lambda f, m: seen.append(f))

    proj = store.load(p.id)
    files = proj.stages["assemble"].output["files"]
    assert any("looping" in w for w in proj.stages["assemble"].output["warnings"])
    for fmt, (w, h) in config.FORMATS.items():
        out = d / files[fmt]
        info = ff.probe(out)
        assert (info["width"], info["height"]) == (w, h)
        assert info.get("has_audio")
        assert frame_count(out) == 120  # 4.0 s at 30 fps, exactly
        assert abs(info["duration"] - 4.0) < 0.1
    assert (d / "captions" / "vertical.ass").exists()
    assert seen and max(seen) <= 1.0
    assert stages.stage_status(proj)["assemble"] == "done"

    # Editing a clip makes the render stale.
    store.update(p.id, lambda proj: setattr(proj.sections[2], "clips",
                                            [Clip(source="game.mp4", t_in=0, t_out=1)]))
    assert stages.stage_status(store.load(p.id))["assemble"] == "stale"


def test_job_queue_saves_safely_from_many_threads():
    import threading

    from app.jobs import JobQueue

    q = JobQueue()
    threads = [threading.Thread(target=lambda: [q._save(force=True) for _ in range(50)]) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert json.loads((config.DATA_DIR / "jobs.json").read_text()) == []
