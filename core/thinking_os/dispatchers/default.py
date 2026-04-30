"""
Coding OS — Default dispatcher (fallback for all non-Claude adapters).

PURPOSE:      When no adapter-native SDK is available (Codex, Cursor, or a
              Claude session without the `claude-sdk` extra installed), the
              supervisor can still work: it records the intended dispatch
              and returns a "skipped" result with enough metadata that the
              main agent can execute the formula itself via tool-use.
INPUT:        DispatchRequest.
OUTPUT:       DispatchResult(status="skipped", output_json={}) plus an
              error field explaining why the agent must self-dispatch.
DEPENDENCIES: dispatcher.py contracts only; no external SDKs.
NOTES:        This preserves backward-compatibility with Phase M behaviour
              — cos_supervise already expected the main agent to call
              cos_supervise_record_output manually.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from thinking_os.dispatcher import DispatchRequest, DispatchResult

logger = logging.getLogger("coding_os.dispatcher.default")


class DefaultDispatcher:
    """
    PURPOSE:      Agent-agnostic fallback. Does NOT spawn a sub-agent;
                  instead returns a DispatchResult that tells the caller
                  to run the formula inline via tool-use.
    NOTES:        `available()` always returns True so factory never
                  explodes. Real spawning happens in adapter dispatchers.
    """
    name = "default"

    def available(self) -> bool:
        return True

    async def dispatch(self, request: DispatchRequest) -> DispatchResult:
        """
        PURPOSE: Record the dispatch intent and return a 'skipped' result.
                 Main-agent is expected to execute the formula itself and
                 call cos_supervise_record_output when done.
        """
        t0 = time.monotonic()
        logger.info(
            "default-dispatcher: formula=%s persona=%s intensity=%s "
            "(no SDK available — main agent must run inline)",
            request.formula_id, request.persona_id, request.intensity,
        )
        payload: dict[str, Any] = {
            "dispatch_hint": (
                "No adapter-native SDK is installed. The main agent should "
                "execute this formula inline by reading agent_file and "
                "producing the EvidenceBundle slice, then calling "
                "cos_supervise_record_output."
            ),
            "agent_file": request.agent_file,
            "formula_id": request.formula_id,
            "intensity": request.intensity,
        }
        return DispatchResult(
            formula_id=request.formula_id,
            status="skipped",
            output_json=payload,
            latency_ms=int((time.monotonic() - t0) * 1000),
            dispatcher_name=self.name,
            error="inline-dispatch-required",
        )
