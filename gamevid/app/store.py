"""One folder per project, with project.json saved atomically.

The API thread and the job worker both write project.json, so every
read-modify-write goes through update(), which holds a per-project lock.
"""

import hashlib
import json
import os
import re
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Callable

from . import config
from .models import Project, now_iso

SUBDIRS = ("footage", "proxies", "audio", "captions", "renders", "cache")

_locks: dict[str, threading.RLock] = {}
_locks_guard = threading.Lock()


def _lock(pid: str) -> threading.RLock:
    with _locks_guard:
        return _locks.setdefault(pid, threading.RLock())


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "video"


def project_dir(pid: str) -> Path:
    if not re.fullmatch(r"[a-z0-9-]+", pid):
        raise ValueError(f"bad project id {pid!r}")
    return config.PROJECTS_DIR / pid


def safe_path(pid: str, rel: str) -> Path:
    """Resolve a path inside a project folder, refusing anything that escapes it."""
    base = project_dir(pid).resolve()
    p = (base / rel).resolve()
    if base != p and base not in p.parents:
        raise ValueError("path escapes project folder")
    return p


def create(title: str, topic: str = "", bullets: list[str] | None = None) -> Project:
    pid = f"{datetime.now():%Y%m%d-%H%M%S}-{slugify(title)}"
    d = project_dir(pid)
    for sub in SUBDIRS:
        (d / sub).mkdir(parents=True, exist_ok=True)
    project = Project(id=pid, title=title, topic=topic, bullets=bullets or [])
    save(project)
    return project


def load(pid: str) -> Project:
    path = project_dir(pid) / "project.json"
    if not path.exists():
        raise FileNotFoundError(pid)
    return Project.model_validate_json(path.read_text(encoding="utf-8"))


def save(project: Project) -> None:
    path = project_dir(project.id) / "project.json"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(project.model_dump_json(indent=2), encoding="utf-8")
    os.replace(tmp, path)


@contextmanager
def editing(pid: str):
    """with editing(pid) as p: mutate p; it is validated and saved on exit."""
    with _lock(pid):
        project = load(pid)
        yield project
        save(Project.model_validate(project.model_dump()))


def update(pid: str, fn: Callable[[Project], None]) -> Project:
    with editing(pid) as p:
        fn(p)
    return load(pid)


def list_projects() -> list[dict]:
    out = []
    if not config.PROJECTS_DIR.exists():
        return out
    for d in sorted(config.PROJECTS_DIR.iterdir(), reverse=True):
        if (d / "project.json").exists():
            try:
                p = load(d.name)
                out.append({"id": p.id, "title": p.title, "created_at": p.created_at})
            except Exception:  # a broken project shouldn't hide the others
                out.append({"id": d.name, "title": f"{d.name} (unreadable)", "created_at": ""})
    return out


def mark_stage(pid: str, stage: str, input_hash: str, output: dict | None = None) -> None:
    from .models import StageState

    def fn(p: Project):
        p.stages[stage] = StageState(input_hash=input_hash, updated_at=now_iso(), output=output)

    update(pid, fn)


def hash_json(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:16]


def file_sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]
