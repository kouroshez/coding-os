"""
Coding OS — Cursor dispatcher (adapters/cursor).

PURPOSE:      Stub dispatcher that satisfies the AgentDispatcher protocol
              for Cursor sessions. Cursor is an IDE without a headless CLI
              and has no Python/TypeScript SDK as of 2026-04, so there is
              no programmatic path to spawn a sub-agent. The dispatcher
              therefore declares itself unavailable; the factory in
              core/thinking_os/dispatcher.py will transparently fall back
              to the DefaultDispatcher (DB-only persistence, no spawn) and
              the main Cursor agent must execute the role inline by
              reading core/thinking_os/agents/<role>.md.
INPUT:        DispatchRequest (passed through but not used).
OUTPUT:       DispatchResult(status="skipped") — caller treats this as a
              signal to inline the role's procedure.
DEPENDENCIES: Core contract imported dynamically from
              core/thinking_os/dispatcher.py (Rule 1 — no core/ imports
              at module level).
NOTES:        Rule 1: this file is Cursor-only and MUST NOT be imported
              from core/. When Cursor ships a programmable headless mode,
              extend `dispatch()` to invoke it and update `available()`.
              Until then, lazy-load is the only sane path.
"""

from __future__ import annotations

import logging

from thinking_os.dispatcher import DispatchRequest, DispatchResult

logger = logging.getLogger("coding_os.dispatcher.cursor")


class CursorDispatcher:
    """
    PURPOSE:      Conformance stub. Declares unavailable; caller falls
                  back to default dispatcher.
    INPUT:        DispatchRequest.
    OUTPUT:       DispatchResult(status="skipped").
    DEPENDENCIES: stdlib only.
    NOTES:        No SDK exists. Lazy-load is the canonical path.
    """

    name = "cursor"

    def available(self) -> bool:  # noqa: D401
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
