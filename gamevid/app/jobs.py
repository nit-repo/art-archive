"""Background job queue: one worker thread, progress, retries, resume on restart.

Jobs are persisted to data/jobs.json. Anything queued or running when the app
stopped is re-queued at startup; stages are idempotent, so re-running is safe.
"""

import json
import os
import queue
import threading
import time
import traceback
import uuid
from dataclasses import asdict, dataclass, field
from typing import Callable

from . import config, stages
from .models import now_iso

# kind -> (function(project_id, progress, **args), max attempts)
HANDLERS: dict[str, tuple[Callable, int]] = {
    "captions": (lambda pid, pr, **a: stages.run_captions(pid, pr), 2),
    "assemble": (lambda pid, pr, **a: stages.run_assemble(pid, pr), 2),
    "proxy": (lambda pid, pr, **a: stages.make_proxy(pid, a["filename"], pr), 2),
}


@dataclass
class Job:
    kind: str
    project_id: str
    args: dict = field(default_factory=dict)
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])
    status: str = "queued"  # queued | running | done | failed
    progress: float = 0.0
    message: str = ""
    attempts: int = 0
    error: str = ""
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)


class JobQueue:
    def __init__(self):
        self._jobs: dict[str, Job] = {}
        self._q: "queue.Queue[str]" = queue.Queue()
        self._lock = threading.Lock()
        self._save_lock = threading.Lock()  # the API thread and the worker both save
        self._file = config.DATA_DIR / "jobs.json"
        self._last_save = 0.0
        self._thread: threading.Thread | None = None

    # ---- persistence
    def _save(self, force: bool = False) -> None:
        now = time.time()
        if not force and now - self._last_save < 1.0:
            return
        self._last_save = now
        with self._lock:
            recent = sorted(self._jobs.values(), key=lambda j: j.created_at)[-200:]
            data = [asdict(j) for j in recent]
        with self._save_lock:
            try:
                tmp = self._file.with_suffix(".tmp")
                tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
                os.replace(tmp, self._file)
            except OSError:
                traceback.print_exc()  # losing job history must never kill the worker

    def start(self) -> None:
        config.ensure_dirs()
        if self._file.exists():
            try:
                for d in json.loads(self._file.read_text(encoding="utf-8")):
                    job = Job(**d)
                    if job.status in ("queued", "running"):
                        job.status, job.message = "queued", "resumed after restart"
                        self._q.put(job.id)
                    self._jobs[job.id] = job
            except (ValueError, TypeError):
                pass  # a corrupt jobs file only loses history
        self._thread = threading.Thread(target=self._worker, daemon=True, name="jobs")
        self._thread.start()

    # ---- public API
    def submit(self, kind: str, project_id: str, **args) -> Job:
        if kind not in HANDLERS:
            raise ValueError(f"unknown job kind {kind}")
        with self._lock:
            for j in self._jobs.values():  # don't queue the same work twice
                if (j.kind, j.project_id, j.args) == (kind, project_id, args) and j.status in ("queued", "running"):
                    return j
            job = Job(kind, project_id, args)
            self._jobs[job.id] = job
        self._q.put(job.id)
        self._save(force=True)
        return job

    def list(self, project_id: str | None = None) -> list[dict]:
        with self._lock:
            jobs = [asdict(j) for j in self._jobs.values()
                    if project_id is None or j.project_id == project_id]
        return sorted(jobs, key=lambda j: j["created_at"], reverse=True)

    # ---- worker
    def _worker(self) -> None:
        while True:
            job = self._jobs[self._q.get()]
            fn, max_attempts = HANDLERS[job.kind]
            job.status, job.attempts, job.error = "running", job.attempts + 1, ""
            job.updated_at = now_iso()
            self._save(force=True)

            def progress(frac: float, msg: str = "", job=job):
                job.progress, job.updated_at = round(frac, 3), now_iso()
                if msg:
                    job.message = msg
                self._save()

            try:
                fn(job.project_id, progress, **job.args)
                job.status, job.progress, job.message = "done", 1.0, "done"
            except Exception as e:  # noqa: BLE001 — every failure is reported to the UI
                traceback.print_exc()
                job.error = str(e)
                if job.attempts < max_attempts and not isinstance(e, (RuntimeError, ValueError)):
                    # Unexpected errors get one retry after a short backoff. RuntimeError and
                    # ValueError mean "fix your inputs", so retrying would just fail again.
                    job.status, job.message = "queued", f"retrying after error: {e}"
                    self._save(force=True)
                    time.sleep(2 ** job.attempts)
                    self._q.put(job.id)
                    continue
                job.status, job.message = "failed", str(e)
            job.updated_at = now_iso()
            self._save(force=True)


jobs = JobQueue()
