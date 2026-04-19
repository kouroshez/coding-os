"""lsp:warm-start role — attach shared pyright / tsserver once (I.9)."""

from __future__ import annotations

import logging

from ...lsp_overlay import LspOverlay, build_overlay
from ..registry import Role, RoleContext, RoleResult

logger = logging.getLogger("graph_os.orchestrator.roles.lsp_warm_start")

ROLE_NAME = "lsp:warm-start"


def _handler(ctx: RoleContext) -> RoleResult:
    language = ctx.args.get("language", "python")
    fake = bool(ctx.args.get("fake", False))
    overlay = ctx.shared.get("lsp_overlay")
    if overlay is None:
        overlay = build_overlay(language, config={"fake": fake})
        ctx.shared["lsp_overlay"] = overlay
    if not isinstance(overlay, LspOverlay):
        return RoleResult(status="error", error="shared.lsp_overlay not an LspOverlay")

    ok = overlay.warm_start()
    snapshot = overlay.snapshot()
    return RoleResult(
        status="ok" if ok else "skipped",
        payload=snapshot,
    )


def build_role() -> Role:
    return Role(
        name=ROLE_NAME,
        handler=_handler,
        description="Attach the shared LSP subprocess once per process.",
        max_concurrency=1,
    )


__all__ = ["ROLE_NAME", "build_role"]
