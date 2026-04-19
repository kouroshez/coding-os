"""Bounded worker pool with cancellation + crash-restart (I.9).

PURPOSE:  Run role handlers in parallel with a fixed concurrency cap,
          surface per-task progress, and restart a worker up to 3
          times on handler crash before quarantining the task.
INPUT:    created with a WorkerPool(size=N).
OUTPUT:   `submit()` returns a Future-like handle with a `.result()`
          method.
DEPENDS:  stdlib threading / queue only — we intentionally avoid
          concurrent.futures so the pool stays cancellable cleanly
          (§13.3 plan: `cos graph-reindex --cancel` sends SIGTERM).
NOTES:    The plan promises "real agent processes, not multiprocessing".
          I.9 ships the thread-based implementation — the multi-
          process agent spawn is wired in I.9b once the orchestrator
          has real telemetry to route.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from queue import Empty, Queue
from typing import Any, Callable

from .registry import RoleContext, RoleResult

logger = logging.getLogger("graph_os.orchestrator.worker_pool")

_SENTINEL = object()


@dataclass
class Task:
    """Unit of work submitted to the pool."""

    task_id: str
    role_name: str
    ctx: RoleContext
    handler: Callable[[RoleContext], RoleResult]
    max_retries: int = 3
    attempts: int = 0
    quarantined: bool = False
    result: RoleResult | None = None
    error: Exception | None = None
    done: threading.Event = field(default_factory=threading.Event)


class WorkerPool:
    """Fixed-size pool that runs Role handlers in parallel threads.

    PURPOSE:      Dispatch worker. Not a Future replacement — exposes
                  the minimal surface orchestrator + tests need.
    INPUT:        pool size (defaults to 4).
    OUTPUT:       submit(...) -> Task; task.done.wait() to block.
    NOTES:        Cancellation is cooperative — set `cancel_event()`
                  and the workers drain without picking up new tasks.
    """

    def __init__(self, size: int = 4, *, name: str = "graph-os-pool") -> None:
        if size < 1:
            raise ValueError("pool size must be >= 1")
        self._size = size
        self._name = name
        self._queue: Queue[Any] = Queue()
        self._workers: list[threading.Thread] = []
        self._cancel = threading.Event()
        self._stats_lock = threading.Lock()
        self.tasks_processed: int = 0
        self.tasks_quarantined: int = 0
        self._start()

    # -- Lifecycle ---------------------------------------------------------

    def _start(self) -> None:
        for i in range(self._size):
            thread = threading.Thread(
                target=self._run,
                name=f"{self._name}-{i}",
                daemon=True,
            )
            thread.start()
            self._workers.append(thread)

    def cancel(self) -> None:
        self._cancel.set()

    def shutdown(self, *, wait: bool = True) -> None:
        self.cancel()
        for _ in self._workers:
            self._queue.put(_SENTINEL)
        if wait:
            for thread in self._workers:
                thread.join(timeout=5.0)

    # -- Public surface ----------------------------------------------------

    def submit(
        self,
        *,
        role_name: str,
        handler: Callable[[RoleContext], RoleResult],
        ctx: RoleContext,
        task_id: str | None = None,
        max_retries: int = 3,
    ) -> Task:
        task = Task(
            task_id=task_id or f"{role_name}:{time.monotonic_ns()}",
            role_name=role_name,
            ctx=ctx,
            handler=handler,
            max_retries=max_retries,
        )
        if self._cancel.is_set():
            task.error = RuntimeError("pool is cancelled")
            task.done.set()
            return task
        self._queue.put(task)
        return task

    def snapshot(self) -> dict[str, Any]:
        with self._stats_lock:
            return {
                "size": self._size,
                "queue_depth": self._queue.qsize(),
                "cancelled": self._cancel.is_set(),
                "tasks_processed": self.tasks_processed,
                "tasks_quarantined": self.tasks_quarantined,
            }

    # -- Internals ---------------------------------------------------------

    def _run(self) -> None:
        while True:
            if self._cancel.is_set():
                return
            try:
                item = self._queue.get(timeout=0.25)
            except Empty:
                continue
            if item is _SENTINEL:
                self._queue.task_done()
                return
            self._handle(item)
            self._queue.task_done()

    def _handle(self, task: Task) -> None:
        while task.attempts < task.max_retries:
            task.attempts += 1
            if self._cancel.is_set():
                task.error = RuntimeError("pool cancelled mid-task")
                task.done.set()
                return
            try:
                started = time.monotonic()
                result = task.handler(task.ctx)
                if result.duration_ms is None:
                    result.duration_ms = int((time.monotonic() - started) * 1000)
                task.result = result
                with self._stats_lock:
                    self.tasks_processed += 1
                task.done.set()
                return
            except Exception as exc:  # noqa: BLE001 — we want to retry
                task.error = exc
                logger.debug(
                    "pool: task %s attempt %d failed: %s",
                    task.task_id,
                    task.attempts,
                    exc,
                )
        task.quarantined = True
        with self._stats_lock:
            self.tasks_quarantined += 1
        task.result = RoleResult(
            status="error",
            error=str(task.error) if task.error else "unknown",
        )
        task.done.set()


__all__ = ["Task", "WorkerPool"]
