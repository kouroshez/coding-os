"""core.web.init_jobs — in-process job tracking for create-from-UI (TASK-362).

A job wraps one `cos init` subprocess: ordered phase events derived from the
init log, a bounded log buffer that survives browser refreshes (the job lives
in the server process, not the request), cancel with partial-scaffold cleanup,
and funnel counters rendered into /api/metrics.
"""

from __future__ import annotations

import shutil
import subprocess
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

# Ordered phases. "validate" completes before the subprocess starts (the
# route validates first); the rest are detected from init's own log lines —
# the markers are init's stable user-facing echoes, not internals.
PHASES: tuple[str, ...] = ("validate", "scaffold", "adapters", "docs-seed", "register", "done")

_PHASE_MARKERS: tuple[tuple[str, str], ...] = (
    ("Initializing coding-os in", "scaffold"),
    ("Created .coding-os", "scaffold"),
    ("Installing", "adapters"),
    ("Applying template:", "docs-seed"),
    ("Composed", "docs-seed"),
    ("Seeded docs/_meta", "docs-seed"),
    ("Registered in hub registry", "register"),
    ("Skipped hub registry write", "register"),
)

_LOG_BUFFER_MAX = 2000

COUNTERS: dict[str, int] = {"started": 0, "succeeded": 0, "failed": 0, "cancelled": 0}
_COUNTER_LOCK = threading.Lock()


def _count(key: str) -> None:
    with _COUNTER_LOCK:
        COUNTERS[key] += 1


def render_counters() -> str:
    """Prometheus text block for the init-job funnel (joined into /api/metrics)."""
    lines = ["# TYPE cos_init_jobs_total counter"]
    with _COUNTER_LOCK:
        for key, value in COUNTERS.items():
            lines.append(f'cos_init_jobs_total{{status="{key}"}} {value}')
    return "\n".join(lines) + "\n"


@dataclass
class InitJob:
    job_id: str
    target: Path
    status: str = "running"  # running | succeeded | failed | cancelled
    phase: str = "validate"
    log: deque = field(default_factory=lambda: deque(maxlen=_LOG_BUFFER_MAX))
    error: str = ""
    result: dict = field(default_factory=dict)
    cleanup: dict = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    _proc: subprocess.Popen | None = None
    _cancel_requested: bool = False
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _version: int = 0  # bumped on every mutation; SSE consumers poll it
    _appended: int = 0  # total lines ever appended (deque is bounded)

    def snapshot(self, log_tail: int = 50) -> dict:
        with self._lock:
            return {
                "job_id": self.job_id,
                "status": self.status,
                "phase": self.phase,
                "phases": list(PHASES),
                "log": list(self.log)[-log_tail:],
                "log_len": len(self.log),
                "error": self.error,
                "result": dict(self.result),
                "cleanup": dict(self.cleanup),
            }

    def log_slice(self, offset: int) -> tuple[list[str], int]:
        """Lines from `offset` (for SSE replay-then-follow). Returns (lines, new_offset).

        The deque is bounded; when `offset` predates the window the replay
        starts at the oldest retained line (documented truncation, never an error)."""
        with self._lock:
            lines = list(self.log)
            dropped = max(0, self._appended - len(lines))
            start = max(0, offset - dropped)
            return lines[start:], dropped + len(lines)

    def _append_log(self, line: str) -> None:
        with self._lock:
            self.log.append(line)
            self._appended += 1
            self._version += 1
            for marker, phase in _PHASE_MARKERS:
                if marker in line and PHASES.index(phase) > PHASES.index(self.phase):
                    self.phase = phase

    def _finish(self, status: str, *, error: str = "", result: dict | None = None) -> None:
        with self._lock:
            self.status = status
            self.phase = "done" if status == "succeeded" else self.phase
            self.error = error
            if result:
                self.result = result
            self._version += 1
        _count(status)


_JOBS: dict[str, InitJob] = {}
_JOBS_LOCK = threading.Lock()


def get_job(job_id: str) -> InitJob | None:
    with _JOBS_LOCK:
        return _JOBS.get(job_id)


def start_job(cmd: list[str], target: Path, cwd: str, parse_payload) -> InitJob:
    """Launch `cmd` as a tracked job; a worker thread streams its output."""
    job = InitJob(job_id=f"job-{uuid.uuid4().hex[:10]}", target=target)
    with _JOBS_LOCK:
        _JOBS[job.job_id] = job
    _count("started")

    def _worker() -> None:
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        except OSError as exc:
            job._finish("failed", error=f"could not launch cos init: {exc}")
            return
        with job._lock:
            job._proc = proc
            job.phase = "scaffold"
            job._version += 1
        stdout_lines: list[str] = []
        assert proc.stdout is not None
        for line in proc.stdout:
            stripped = line.rstrip("\n")
            stdout_lines.append(stripped)
            job._append_log(stripped)
            if job._cancel_requested:
                break

        if job._cancel_requested:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
            removed = False
            if target.exists():
                shutil.rmtree(target, ignore_errors=True)
                removed = True
            with job._lock:
                job.cleanup = {"removed_dir": str(target) if removed else None}
            job._finish("cancelled")
            return

        returncode = proc.wait()
        if returncode != 0:
            removed = False
            if target.exists():
                shutil.rmtree(target, ignore_errors=True)
                removed = True
            with job._lock:
                job.cleanup = {"removed_dir": str(target) if removed else None}
            tail = "\n".join(stdout_lines[-8:])
            job._finish("failed", error=tail or f"init exited {returncode}")
            return

        job._finish("succeeded", result=parse_payload(stdout_lines) or {})

    threading.Thread(target=_worker, name=f"init-{job.job_id}", daemon=True).start()
    return job


def cancel_job(job_id: str) -> InitJob | None:
    """Request cancellation; the worker terminates the subprocess + cleans up."""
    job = get_job(job_id)
    if job is None:
        return None
    with job._lock:
        if job.status == "running":
            job._cancel_requested = True
            if job._proc is not None:
                job._proc.terminate()
    return job


def gc_jobs(max_age_secs: float = 3600.0) -> int:
    """Drop terminal jobs older than `max_age_secs` (bounded memory)."""
    cutoff = time.time() - max_age_secs
    removed = 0
    with _JOBS_LOCK:
        for job_id in [
            j for j, job in _JOBS.items() if job.status != "running" and job.created_at < cutoff
        ]:
            del _JOBS[job_id]
            removed += 1
    return removed
