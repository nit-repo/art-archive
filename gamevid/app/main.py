"""FastAPI app: JSON API plus the static single-page UI."""

import re
import shutil
from typing import Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config, stages, store
from .jobs import jobs
from .models import CaptionStyle, Clip, Music, Section, SectionAudio, Styles
from .timeline import build_timeline

app = FastAPI(title="gamevid")
AUDIO_EXT = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac", ".webm"}
VIDEO_EXT = {".mp4", ".mkv", ".mov", ".webm", ".avi", ".flv"}


@app.on_event("startup")
def _startup():
    config.ensure_dirs()
    jobs.start()


def _load(pid: str):
    try:
        return store.load(pid)
    except (FileNotFoundError, ValueError):
        raise HTTPException(404, "project not found")


def _view(pid: str) -> dict:
    p = _load(pid)
    try:
        tl, tl_error = build_timeline(p).to_dict(), None
    except ValueError as e:
        tl, tl_error = None, str(e)
    return {"project": p.model_dump(), "timeline": tl, "timeline_error": tl_error,
            "stage_status": stages.stage_status(p)}


def _save_upload(upload: UploadFile, dest) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "wb") as f:
        shutil.copyfileobj(upload.file, f, length=4 << 20)


def _safe_name(name: str) -> str:
    stem, dot, ext = (name or "file").rpartition(".")
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem or ext)[:60]
    return f"{stem}.{ext.lower()}" if dot else stem


# ------------------------------------------------------------------ projects

class NewProject(BaseModel):
    title: str
    topic: str = ""
    bullets: list[str] = []


@app.get("/api/projects")
def list_projects():
    return store.list_projects()


@app.post("/api/projects")
def create_project(body: NewProject):
    if not body.title.strip():
        raise HTTPException(400, "title is required")
    return _view(store.create(body.title.strip(), body.topic, body.bullets).id)


@app.get("/api/projects/{pid}")
def get_project(pid: str):
    return _view(pid)


class SectionIn(BaseModel):
    id: Optional[str] = None
    kind: str = "body"
    text: str = ""


@app.put("/api/projects/{pid}/sections")
def put_sections(pid: str, body: list[SectionIn]):
    """Replace section text/kinds, keeping clips and timings for sections that still exist."""
    _load(pid)

    def fn(p):
        old = {s.id: s for s in p.sections}
        used = set()
        new = []
        for i, s in enumerate(body):
            sid = s.id if s.id in old and s.id not in used else None
            if sid is None:
                n = 1
                while f"s{n}" in old or f"s{n}" in used:
                    n += 1
                sid = f"s{n}"
            used.add(sid)
            prev = old.get(sid)
            new.append(Section(id=sid, kind=s.kind, text=s.text.strip(),
                               clips=prev.clips if prev else [],
                               audio=prev.audio if prev and i < len(p.sections) else None))
        p.sections = new
        if len(new) != len(old):  # section count changed: old timings no longer line up
            for s in p.sections:
                s.audio = None

    store.update(pid, fn)
    return _view(pid)


@app.put("/api/projects/{pid}/sections/{sid}/clips")
def put_clips(pid: str, sid: str, clips: list[Clip]):
    p = _load(pid)
    for c in clips:
        info = p.footage.get(c.source)
        if info is None:
            raise HTTPException(400, f"unknown footage {c.source}")
        if c.t_out > info["duration"] + 0.05:
            raise HTTPException(400, f"out point {c.t_out:.2f}s is past the end of {c.source}")

    def fn(proj):
        sec = next((s for s in proj.sections if s.id == sid), None)
        if sec is None:
            raise HTTPException(404, "section not found")
        sec.clips = clips

    store.update(pid, fn)
    return _view(pid)


class Boundary(BaseModel):
    start: float


@app.put("/api/projects/{pid}/sections/{sid}/start")
def put_section_start(pid: str, sid: str, body: Boundary):
    """Manually nudge where a section starts on the narration."""
    def fn(p):
        sec = next((s for s in p.sections if s.id == sid), None)
        if sec is None:
            raise HTTPException(404, "section not found")
        sec.audio = SectionAudio(start=max(0.0, body.start), source="manual")

    store.update(pid, fn)
    return _view(pid)


class Settings(BaseModel):
    styles: Optional[Styles] = None
    music: Optional[Music] = None
    formats: Optional[list[str]] = None


@app.put("/api/projects/{pid}/settings")
def put_settings(pid: str, body: Settings):
    def fn(p):
        if body.styles:
            p.styles = body.styles
        if body.music:
            p.music = body.music
        if body.formats is not None:
            if not body.formats or not set(body.formats) <= set(config.FORMATS):
                raise HTTPException(400, "formats must be vertical and/or horizontal")
            p.formats = body.formats

    store.update(pid, fn)
    return _view(pid)


# ------------------------------------------------------------------ uploads

@app.post("/api/projects/{pid}/narration")
def upload_narration(pid: str, file: UploadFile = File(...)):
    _load(pid)
    name = _safe_name(file.filename)
    if "." + name.rsplit(".", 1)[-1] not in AUDIO_EXT | VIDEO_EXT:
        raise HTTPException(400, "unsupported audio format")
    raw = store.project_dir(pid) / "audio" / f"upload-{name}"
    _save_upload(file, raw)
    try:
        stages.import_narration(pid, raw)
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    finally:
        raw.unlink(missing_ok=True)
    return _view(pid)


@app.post("/api/projects/{pid}/footage")
def upload_footage(pid: str, file: UploadFile = File(...)):
    _load(pid)
    name = _safe_name(file.filename)
    if "." + name.rsplit(".", 1)[-1] not in VIDEO_EXT:
        raise HTTPException(400, "unsupported video format")
    _save_upload(file, store.safe_path(pid, f"footage/{name}"))
    jobs.submit("proxy", pid, filename=name)
    return _view(pid)


@app.delete("/api/projects/{pid}/footage/{name}")
def delete_footage(pid: str, name: str):
    p = _load(pid)
    if any(c.source == name for s in p.sections for c in s.clips):
        raise HTTPException(400, "footage is used by a section; remove those clips first")
    store.safe_path(pid, f"footage/{name}").unlink(missing_ok=True)
    store.safe_path(pid, f"proxies/{name}.mp4").unlink(missing_ok=True)
    store.update(pid, lambda proj: proj.footage.pop(name, None))
    return _view(pid)


@app.get("/api/projects/{pid}/file/{rel:path}")
def get_file(pid: str, rel: str):
    try:
        path = store.safe_path(pid, rel)
    except ValueError:
        raise HTTPException(400, "bad path")
    if not path.is_file():
        raise HTTPException(404, "not found")
    return FileResponse(path)


@app.get("/api/projects/{pid}/captions")
def get_captions(pid: str):
    path = store.project_dir(pid) / "captions" / "words.json"
    if not path.exists():
        return {"words": []}
    return FileResponse(path, media_type="application/json")


# ------------------------------------------------------------------ jobs & music

@app.post("/api/projects/{pid}/jobs/{kind}")
def start_job(pid: str, kind: str):
    _load(pid)
    if kind not in ("captions", "assemble"):
        raise HTTPException(400, "unknown stage")
    return jobs.submit(kind, pid).__dict__


@app.get("/api/jobs")
def list_jobs(project: Optional[str] = None):
    return jobs.list(project)


@app.get("/api/music")
def list_music():
    if not config.MUSIC_DIR.exists():
        return []
    return sorted(f.name for f in config.MUSIC_DIR.iterdir()
                  if f.suffix.lower() in {".mp3", ".wav", ".m4a", ".ogg", ".flac"})


@app.get("/api/defaults")
def defaults():
    return {"styles": Styles().model_dump(), "caption_style": CaptionStyle().model_dump(),
            "whisper": {"mode": config.WHISPER_MODE, "model": config.WHISPER_MODEL}}


app.mount("/", StaticFiles(directory=config.STATIC_DIR, html=True), name="static")
