"""Dispatcher — route tasks to roles + drive the worker pool (I.9).

PURPOSE:  Thin layer above the worker pool that looks up the role by
          name, builds a RoleContext, and submits work. Cancellation,
          progress metrics, and role-name validation all live here so
          each role handler stays narrow.
INPUT:    a registry + a worker pool.
OUTPUT:   dispatch(task_payloads) → list[Task].
DEPENDS:  registry, worker_pool, progress.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Iterable

from .progress import ProgressReporter
from .registry import RoleContext, RoleRegistry, RoleResult
from .worker_pool import Task, WorkerPool

logger = logging.getLogger("graph_os.orchestrator.dispatcher")


@dataclass
class Dispatcher:
    registry: RoleRegistry
    pool: WorkerPool
    progress: ProgressReporter = field(default_factory=ProgressReporter)

    def dispatch(
        self,
        role_name: str,
        *,
        args: dict[str, Any] | None = None,
        shared: dict[str, Any] | None = None,
        task_id: str | None = None,
    ) -> Task:
        role = self.registry.resolve(role_name)
        ctx = RoleContext(
            role_name=role_name,
            args=args or {},
            shared=shared or {},
        )
        self.progress.record("dispatch.submitted", role=role_name)
        task = self.pool.submit(
            role_name=role_name,
            handler=role.handler,
            ctx=ctx,
            task_id=task_id,
        )
        return task

    def dispatch_many(
        self,
        role_name: str,
        payloads: Iterable[dict[str, Any]],
        *,
        shared: dict[str, Any] | None = None,
    ) -> list[Task]:
        """Fan out many args dicts to the same role."""
        return [
            self.dispatch(role_name, args=payload, shared=shared)
            for payload in payloads
        ]

    def wait_all(self, tasks: list[Task], *, timeout: float | None = None) -> list[RoleResult]:
        out: list[RoleResult] = []
        for task in tasks:
            task.done.wait(timeout=timeout)
            if task.result is None:
                out.append(RoleResult(status="error", error="no result"))
            else:
                out.append(task.result)
        return out

    def cancel_all(self) -> None:
        self.progress.record("dispatch.cancelled", count=1)
        self.pool.cancel()


__all__ = ["Dispatcher"]
