"""Coding OS — Cursor dispatcher (adapters/cursor)."""

from __future__ import annotations

import logging

from thinking_os.dispatcher import DispatchRequest, DispatchResult

logger = logging.getLogger("coding_os.dispatcher.cursor")


class CursorDispatcher:
    name = "cursor"

    def available(self) -> bool:
        """Cursor has no programmable spawn path; always unavailable."""
        return False

    async def dispatch(self, request: DispatchRequest) -> DispatchResult:
        """Return skipped — caller must inline the role.

        Kept as `async def` so the AgentDispatcher Protocol is satisfied;
        in practice the factory short-circuits on `available()` returning
        False, and this method should never run.
        """
        logger.debug(
            "CursorDispatcher.dispatch called for role=%s — returning skipped",
            request.formula_id,
        )
        return DispatchResult(
            formula_id=request.formula_id,
            status="skipped",
            output_json={},
            latency_ms=0,
            error="Cursor has no headless dispatcher; inline the role",
            dispatcher_name=self.name,
        )


def build_dispatcher() -> CursorDispatcher:
    """Factory imported by core/thinking_os/dispatcher.py via importlib."""
    return CursorDispatcher()
