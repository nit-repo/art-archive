"""Thin ffmpeg/ffprobe wrappers: probing, running with progress, path escaping."""

import json
import subprocess
from pathlib import Path
from typing import Callable, Optional

from . import config

# Hide the console window that would otherwise flash up for every call on Windows.
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class FFmpegError(RuntimeError):
    pass


def probe(path: Path) -> dict:
    out = subprocess.run(
        [config.FFPROBE, "-v", "error", "-print_format", "json",
         "-show_format", "-show_streams", str(path)],
        capture_output=True, text=True, creationflags=_NO_WINDOW,
    )
    if out.returncode != 0:
        raise FFmpegError(f"ffprobe failed on {path.name}: {out.stderr.strip()[-500:]}")
    data = json.loads(out.stdout)
    info = {"duration": float(data.get("format", {}).get("duration", 0) or 0)}
    for s in data.get("streams", []):
        if s.get("codec_type") == "video" and "width" not in info:
            num, _, den = (s.get("avg_frame_rate") or "0/1").partition("/")
            info.update(width=s["width"], height=s["height"],
                        fps=round(float(num) / float(den or 1), 3) if float(den or 1) else 0)
        if s.get("codec_type") == "audio":
            info["has_audio"] = True
    return info


def run(args: list[str], *, cwd: Optional[Path] = None, duration: float = 0,
        on_progress: Optional[Callable[[float], None]] = None) -> None:
    """Run ffmpeg; report 0..1 progress when the expected output duration is known."""
    cmd = [config.FFMPEG, "-hide_banner", "-nostdin", "-y", "-progress", "pipe:1", "-nostats", *args]
    proc = subprocess.Popen(
        cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace", creationflags=_NO_WINDOW,
    )
    # Drain stderr on a thread so a chatty ffmpeg can't block on a full pipe.
    import threading
    err_lines: list[str] = []
    t = threading.Thread(target=lambda: err_lines.extend(proc.stderr), daemon=True)
    t.start()
    for line in proc.stdout:
        if on_progress and duration > 0 and line.startswith("out_time_us="):
            try:
                us = int(line.split("=", 1)[1])
                on_progress(min(1.0, us / 1e6 / duration))
            except ValueError:
                pass
    proc.wait()
    t.join(timeout=5)
    if proc.returncode != 0:
        tail = "".join(err_lines[-15:]).strip()
        raise FFmpegError(f"ffmpeg exited {proc.returncode}: {tail}")


def filter_path(path: Path | str) -> str:
    """Quote a path for use inside an ffmpeg filter argument (handles Windows 'C:\\')."""
    s = str(path).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
    return f"'{s}'"
