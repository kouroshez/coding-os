"""Coding OS — Default dispatcher (fallback for all non-Claude adapters)."""

from __future__ import annotations

import logging
import time
from typing import Any

from thinking_os.dispatcher import DispatchRequest, DispatchResult

logger = logging.getLogger("coding_os.dispatcher.default")


class DefaultDispatcher:
    name = "default"

    def available(self) -> bool:
        return True

    async def dispatch(self, request: DispatchRequest) -> DispatchResult:
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
