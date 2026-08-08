"""
Coding OS — Background continuous indexer.

A thin, opt-in, thread-based loop that keeps the brain fresh without
requiring the agent to run `make docs-index` / `make task-sync` manually.

Activation:
    Opt-in via `COS_BACKGROUND_INDEX=1` (default OFF — never surprise
    consumer projects with a thread they didn't ask for).

Loop (every COS_BACKGROUND_INTERVAL seconds, default 300):
    1. docs index — mtime-incremental; >99% of files skip cheaply.
    2. tasks sync — mtime-incremental status + structure.
    3. Record result to internal state dict exposed via BackgroundIndexer.status().

Safety:
    - Failure counter: three consecutive failures → loop disables itself
      and sets `disabled_reason` so cos_health can surface it.
    - Stop event: `BackgroundIndexer.stop()` returns cleanly within one
      tick for graceful MCP shutdown.
    - Sleep uses the stop event (not time.sleep) so shutdown is immediate.
    - Single-process: if the loop is somehow instantiated twice,
      `start()` is idempotent and returns the existing thread.
    - Zero external dependencies beyond stdlib threading.

cos_health exposes:
    {background_indexer: {enabled, running, last_run_at, last_duration_ms,
      last_error, consecutive_failures, disabled_reason, iterations}}
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("coding_os.background")


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

ENV_ENABLED = "COS_BACKGROUND_INDEX"
ENV_INTERVAL = "COS_BACKGROUND_INTERVAL"

DEFAULT_INTERVAL_SECONDS = 300  # 5 min between passes
_MIN_INTERVAL_SECONDS = 30  # prevent accidental hot-loop
_MAX_INTERVAL_SECONDS = 3600  # sanity cap
_MAX_CONSECUTIVE_FAILURES = 3


def is_enabled() -> bool:
    """Return True iff COS_BACKGROUND_INDEX is set to a truthy value."""
    v = os.environ.get(ENV_ENABLED, "")
    return v.strip().lower() in {"1", "true", "yes", "on"}


def _parse_interval() -> int:
    """Clamp the user-configured interval into [30s, 3600s]."""
    raw = os.environ.get(ENV_INTERVAL, "")
    if not raw.strip():
        return DEFAULT_INTERVAL_SECONDS
    try:
        v = int(raw)
    except ValueError:
        return DEFAULT_INTERVAL_SECONDS
    return max(_MIN_INTERVAL_SECONDS, min(_MAX_INTERVAL_SECONDS, v))


def _project_root() -> Path:
    """Resolve the project root for passing to indexer/task_sync.

    Delegates to the canonical database.project_root() (COS_PROJECT_ROOT >
    absolute COS_STATE_DIR parent > upward marker-walk).
    """
    from thinking_os.database import project_root

    return project_root()


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


@dataclass
class BackgroundStatus:
    """Snapshot of indexer health for cos_health.

    NOTES: Field shape is stable — the MCP tool serializes this dict
    directly so any new field must preserve the existing keys.
    """

    enabled: bool
    running: bool
    iterations: int = 0
    last_run_at: str | None = None
    last_duration_ms: int | None = None
    last_error: str | None = None
    consecutive_failures: int = 0
    disabled_reason: str | None = None
    next_run_in_seconds: int | None = None
    last_stats: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Indexer
# ---------------------------------------------------------------------------


class BackgroundIndexer:
    """Thread-managed periodic docs-index + task-sync runner.

    Singleton semantics via the module-level `get_indexer()` factory.
    Direct instantiation is supported for tests (pass custom callables
    and interval via constructor).
    """

    def __init__(
        self,
        *,
        interval_seconds: int = DEFAULT_INTERVAL_SECONDS,
        run_docs_index: Callable[[], dict] | None = None,
        run_task_sync: Callable[[], dict] | None = None,
        run_graph_index: Callable[[], dict] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.interval_seconds = max(
            _MIN_INTERVAL_SECONDS,
            min(_MAX_INTERVAL_SECONDS, interval_seconds),
        )
        self._run_docs_index = run_docs_index or _default_docs_index_runner
        self._run_task_sync = run_task_sync or _default_task_sync_runner
        self._run_graph_index = run_graph_index or _default_graph_index_runner
        self._clock = clock

        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

        self._status = BackgroundStatus(enabled=True, running=False)
        self._loop_start_monotonic: float | None = None

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> bool:
        """Start the loop. Idempotent — returns False if already running."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return False
            self._stop_event.clear()
            self._status.running = True
            self._status.disabled_reason = None
            self._thread = threading.Thread(
                target=self._run,
                name="cos-bg-indexer",
                daemon=True,
            )
            self._thread.start()
            return True

    def stop(self, timeout: float = 5.0) -> bool:
        """Signal the loop to stop; block up to `timeout` for clean exit."""
        with self._lock:
            t = self._thread
        if t is None:
            return True
        self._stop_event.set()
        t.join(timeout=timeout)
        alive = t.is_alive()
        with self._lock:
            if not alive:
                self._status.running = False
                self._thread = None
        return not alive

    def status(self) -> dict:
        """Return a JSON-serializable status snapshot."""
        with self._lock:
            s = self._status
            # Compute next-run hint if currently sleeping
            next_in = None
            if s.running and self._loop_start_monotonic is not None:
                elapsed = self._clock() - self._loop_start_monotonic
                next_in = max(0, int(self.interval_seconds - (elapsed % self.interval_seconds)))
            return {
                "enabled": s.enabled,
                "running": s.running,
                "iterations": s.iterations,
                "last_run_at": s.last_run_at,
                "last_duration_ms": s.last_duration_ms,
                "last_error": s.last_error,
                "consecutive_failures": s.consecutive_failures,
                "disabled_reason": s.disabled_reason,
                "next_run_in_seconds": next_in,
                "last_stats": dict(s.last_stats),
                "interval_seconds": self.interval_seconds,
            }

    # -- tick --------------------------------------------------------------

    def run_once(self) -> dict:
        """Execute one iteration synchronously (used by tests + first tick).

        Returns the per-iteration stats dict; never raises — errors are
        captured onto `_status.last_error` and the failure counter.
        """
        start = self._clock()
        iter_stats: dict = {}
        err: str | None = None

        try:
            docs_stats = self._run_docs_index()
            iter_stats["docs"] = docs_stats
        except Exception as exc:
            logger.warning("background docs_index failed: %s", exc)
            err = f"docs_index: {type(exc).__name__}: {exc}"

        try:
            task_stats = self._run_task_sync()
            iter_stats["tasks"] = task_stats
        except Exception as exc:
            logger.warning("background task_sync failed: %s", exc)
            err = f"{err + '; ' if err else ''}task_sync: {type(exc).__name__}: {exc}"

        # graph_os keeps pace with code/doc edits in sessions
        # that don't get PostToolUse (Codex). Runner is content-hash aware
        # so the 99% no-op case is cheap.
        try:
            graph_stats = self._run_graph_index()
            iter_stats["graph"] = graph_stats
        except Exception as exc:
            logger.warning("background graph_index failed: %s", exc)
            err = f"{err + '; ' if err else ''}graph_index: {type(exc).__name__}: {exc}"

        duration_ms = int((self._clock() - start) * 1000)
        from datetime import datetime, timezone

        now_iso = datetime.now(timezone.utc).isoformat()

        with self._lock:
            self._status.iterations += 1
            self._status.last_run_at = now_iso
            self._status.last_duration_ms = duration_ms
            self._status.last_stats = iter_stats
            if err is None:
                self._status.consecutive_failures = 0
                self._status.last_error = None
            else:
                self._status.consecutive_failures += 1
                self._status.last_error = err
                if self._status.consecutive_failures >= _MAX_CONSECUTIVE_FAILURES:
                    self._status.disabled_reason = (
                        f"disabled after {_MAX_CONSECUTIVE_FAILURES} consecutive failures: {err}"
                    )
                    self._stop_event.set()

        return iter_stats

    # -- thread loop -------------------------------------------------------

    def _run(self) -> None:
        self._loop_start_monotonic = self._clock()
        while not self._stop_event.is_set():
            self.run_once()
            # Use event.wait for sleep so stop() returns quickly
            self._stop_event.wait(timeout=float(self.interval_seconds))

        with self._lock:
            self._status.running = False


# ---------------------------------------------------------------------------
# Default runners (wrap the real indexer + task_sync with safe fallbacks)
# ---------------------------------------------------------------------------


def _default_docs_index_runner() -> dict:
    """Run doc_indexer.index_docs against the configured project root."""
    try:
        import doc_indexer
        from database import init_db
    except ImportError as exc:
        return {"status": "skipped", "reason": f"import: {exc}"}

    project_root = _project_root()
    config_path = project_root / ".coding-os" / "rag-config.yaml"
    if not config_path.exists():
        return {"status": "skipped", "reason": f"no rag-config at {config_path}"}

    conn = init_db(os.environ.get("COS_DB_PATH"))
    try:
        stats = doc_indexer.index_docs(
            conn,
            config_path=config_path,
            project_root=project_root,
            force=False,
        )
        return {"status": "ok", "stats": stats}
    finally:
        conn.close()


def _default_task_sync_runner() -> dict:
    """Run task_sync.sync against the configured project root."""
    try:
        import task_sync
        from database import init_db
    except ImportError as exc:
        return {"status": "skipped", "reason": f"import: {exc}"}

    project_root = _project_root()
    tasks_dir = project_root / "docs" / "tasks"
    if not tasks_dir.exists():
        return {"status": "skipped", "reason": f"no tasks/ at {tasks_dir}"}

    conn = init_db(os.environ.get("COS_DB_PATH"))
    try:
        stats = task_sync.sync(conn, project_root=project_root)
        return {"status": "ok", "stats": stats}
    finally:
        conn.close()


def _default_graph_index_runner() -> dict:
    """Run graph_indexer.index_project against the configured project root."""
    try:
        import graph_indexer
    except ImportError as exc:
        return {"status": "skipped", "reason": f"import: {exc}"}

    project_root = _project_root()
    if not project_root.exists():
        return {"status": "skipped", "reason": f"no project_root at {project_root}"}

    db_path = os.environ.get("COS_DB_PATH", str(project_root / ".coding-os" / "coding-os.db"))
    max_files_raw = os.environ.get("COS_BACKGROUND_GRAPH_MAX_FILES", "")
    try:
        max_files = int(max_files_raw) if max_files_raw.strip() else 20_000
    except ValueError:
        max_files = 20_000

    backend = graph_indexer.open_backend(db_path)
    try:
        report = graph_indexer.index_project(
            backend=backend,
            project_root=project_root,
            force=False,
            max_files=max_files,
        )
        return {"status": "ok", "stats": report.to_dict()}
    finally:
        try:
            backend.close()
        except Exception as exc:
            logger.debug("graph backend close suppressed: %s", exc)


# ---------------------------------------------------------------------------
# Singleton accessor (used by server.py on_startup)
# ---------------------------------------------------------------------------

_singleton: BackgroundIndexer | None = None
_singleton_lock = threading.Lock()


def get_indexer() -> BackgroundIndexer:
    """Return the process-wide BackgroundIndexer, creating it on first call."""
    global _singleton
    with _singleton_lock:
        if _singleton is None:
            _singleton = BackgroundIndexer(interval_seconds=_parse_interval())
        return _singleton


def maybe_start_indexer() -> dict:
    """Start the indexer iff COS_BACKGROUND_INDEX=1. Return a status dict."""
    if not is_enabled():
        return {
            "started": False,
            "reason": f"{ENV_ENABLED} not set (opt-in)",
            "status": BackgroundStatus(enabled=False, running=False).__dict__,
        }
    indexer = get_indexer()
    started = indexer.start()
    return {
        "started": started,
        "reason": "ok" if started else "already running",
        "status": indexer.status(),
    }


def reset_singleton_for_tests() -> None:
    """Tear down the module-level singleton — tests ONLY."""
    global _singleton
    with _singleton_lock:
        if _singleton is not None:
            _singleton.stop(timeout=2.0)
            _singleton = None
