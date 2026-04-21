"""migrator:embeddings role — one batch of BGE-M3 re-embedding (I.9)."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from ..registry import Role, RoleContext, RoleResult

logger = logging.getLogger("graph_os.orchestrator.roles.migrator_embeddings")

ROLE_NAME = "migrator:embeddings"


def _ensure_thinking_os_on_path() -> None:
    here = Path(__file__).resolve()
    target = here.parent.parent.parent.parent / "thinking_os"
    if target.exists() and str(target) not in sys.path:
        sys.path.insert(0, str(target))


def _handler(ctx: RoleContext) -> RoleResult:
    conn = ctx.shared.get("conn")
    if conn is None:
        return RoleResult(status="error", error="shared.conn missing")
    _ensure_thinking_os_on_path()
    import migrator_embeddings  # type: ignore

    target = ctx.args.get("target_model", migrator_embeddings.DEFAULT_TARGET_MODEL)
    batch = int(ctx.args.get("batch_size", migrator_embeddings.DEFAULT_BATCH_SIZE))
    checkpoint = ctx.args.get("checkpoint_path", migrator_embeddings.DEFAULT_CHECKPOINT)
    report = migrator_embeddings.run_one_batch(
        conn,
        target_model=target,
        batch_size=batch,
        checkpoint_path=checkpoint,
    )
    status = "ok" if report["migrated_this_batch"] >= 0 else "skipped"
    if report.get("remaining", 1) == 0:
        status = "ok"
    return RoleResult(status=status, payload=report)


def build_role() -> Role:
    return Role(
        name=ROLE_NAME,
        handler=_handler,
        description="Run one batch of the MiniLM → BGE-M3 re-embed.",
        max_concurrency=1,
    )


__all__ = ["ROLE_NAME", "build_role"]
