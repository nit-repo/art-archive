"""Settings from .env and well-known paths. Everything else imports from here."""

import os
import shutil
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

PROJECTS_DIR = Path(os.getenv("PROJECTS_DIR", ROOT / "projects"))
MUSIC_DIR = ROOT / "music"
FONTS_DIR = ROOT / "fonts"
DATA_DIR = ROOT / "data"
STATIC_DIR = Path(__file__).resolve().parent / "static"

HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8000"))

WHISPER_MODE = os.getenv("WHISPER_MODE", "local")  # local | api
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# Cleanup: how many finished renders to keep per project.
KEEP_RENDERS = int(os.getenv("KEEP_RENDERS", "2"))

# Output formats: name -> (width, height).
FORMATS = {"vertical": (1080, 1920), "horizontal": (1920, 1080)}


def _tool(env_name: str, exe: str) -> str:
    path = os.getenv(env_name) or shutil.which(exe)
    return path or exe


FFMPEG = _tool("FFMPEG_PATH", "ffmpeg")
FFPROBE = _tool("FFPROBE_PATH", "ffprobe")


def ensure_dirs() -> None:
    for d in (PROJECTS_DIR, MUSIC_DIR, FONTS_DIR, DATA_DIR):
        d.mkdir(parents=True, exist_ok=True)
