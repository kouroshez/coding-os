"""
Coding OS — Claude-SDK dispatcher (adapters/claude).

PURPOSE:      Real formula-agent spawning for Claude sessions via the
              official claude-agent-sdk. Translates DispatchRequest →
              ClaudeAgentOptions, runs the agent, and collects text blocks
              into a DispatchResult. Enables Phase M formulas (F1..F11) to
              execute as actual Claude Code sub-agents rather than being
              inlined by the main agent.
INPUT:        DispatchRequest built by cos_supervise / cos_dispatch_formula.
OUTPUT:       DispatchResult with parsed JSON output_json, latency_ms.
DEPENDENCIES: claude-agent-sdk (optional extra), anyio. Core contract
              imported dynamically from core/thinking_os/dispatcher.py so
              this module can live under adapters/ without breaking Rule 1.
NOTES:        Rule 1: core/ stays agent-agnostic. This file is Claude-only
              and MUST NOT be imported from core/. The factory in
              core/thinking_os/dispatcher.py loads it by path at runtime.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import sys
import time
from pathlib import Path
from typing import Any

# Load the core Protocol/contracts dynamically. core/thinking_os is on
# sys.path when the MCP server runs; for standalone testing we inject it.
_CORE_TOS = Path(__file__).resolve().parent.parent.parent / "core" / "thinking_os"
if str(_CORE_TOS) not in sys.path:
    sys.path.insert(0, str(_CORE_TOS))

from dispatcher import DispatchRequest, DispatchResult  # noqa: E402

logger = logging.getLogger("coding_os.dispatcher.claude_sdk")


# ---------------------------------------------------------------------------
# Agent-file → system prompt loader
# ---------------------------------------------------------------------------

def _load_agent_prompt(agent_file: str) -> tuple[str, dict[str, Any]]:
    """
    PURPOSE: Read F<N>_<name>.md, split frontmatter from body, return
             (body_prompt, frontmatter_dict).
    """
    path = Path(agent_file)
    if not path.is_absolute():
        path = _CORE_TOS / agent_file.lstrip("/")
    if not path.exists():
        raise FileNotFoundError(f"agent file not found: {agent_file}")

    text = path.read_text()
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            import yaml  # local import — only needed for real dispatch
            meta = yaml.safe_load(parts[1]) or {}
            return parts[2].strip(), meta
    return text.strip(), {}


def _extract_json_block(transcript: str) -> dict[str, Any]:
    """
    PURPOSE: Find the first fenced ```json ... ``` block in the agent's
             transcript and parse it. Formula-agents are instructed to
             emit their EvidenceBundle slice inside such a block.
    NOTES:   Falls back to {} on parse failure — caller treats that as a
             validation error, not a crash.
    """
    m = re.search(r"```json\s*(\{.*?\})\s*```", transcript, re.DOTALL)
    if not m:
        # Try a bare JSON object as a last resort
        m = re.search(r"(\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})", transcript, re.DOTALL)
        if not m:
            return {}
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError as exc:
        logger.debug("JSON parse failed: %s", exc)
        return {}


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

class ClaudeSDKDispatcher:
    """
    PURPOSE:      Spawn a formula-agent as a real Claude Code sub-session
                  via claude-agent-sdk.query().
    NOTES:        available() returns False if the SDK import fails, so the
                  factory transparently falls back to the default dispatcher.
    """
    name = "claude-sdk"

    def __init__(self) -> None:
        self._sdk_ok = False
        self._import_error: str | None = None
        try:
            import claude_agent_sdk  # noqa: F401
            self._sdk_ok = True
        except ImportError as exc:
            self._import_error = str(exc)

    def available(self) -> bool:
        return self._sdk_ok

    async def dispatch(self, request: DispatchRequest) -> DispatchResult:
        t0 = time.monotonic()
        if not self._sdk_ok:
            return DispatchResult(
                formula_id=request.formula_id,
                status="error",
                error=f"claude-agent-sdk not importable: {self._import_error}",
                dispatcher_name=self.name,
                latency_ms=int((time.monotonic() - t0) * 1000),
            )

        from claude_agent_sdk import (
            AssistantMessage,
            ClaudeAgentOptions,
            ResultMessage,
            TextBlock,
            query,
        )

        try:
            system_prompt_body, _meta = _load_agent_prompt(request.agent_file)
        except FileNotFoundError as exc:
            return DispatchResult(
                formula_id=request.formula_id,
                status="error",
                error=str(exc),
                dispatcher_name=self.name,
                latency_ms=int((time.monotonic() - t0) * 1000),
            )

        system_prompt = (
            f"{system_prompt_body}\n\n"
            f"## Dispatch Context\n"
            f"- Formula: {request.formula_id}\n"
            f"- Persona: {request.persona_id or 'n/a'}\n"
            f"- Intensity: {request.intensity}\n\n"
            f"## Instruction\n"
            f"Produce the EvidenceBundle slice for this formula as a single "
            f"```json ... ``` block at the end of your response. Do not wrap "
            f"it in additional prose."
        )
        user_prompt = (
            f"Input slice (upstream formulas only):\n"
            f"```json\n{json.dumps(request.input_slice, indent=2, default=str)}\n```\n\n"
            f"{request.prompt}"
        )

        options = ClaudeAgentOptions(
            system_prompt=system_prompt,
            max_turns=1,
            allowed_tools=list(request.allowed_tools) or [],
            cwd=request.cwd,
        )

        transcript_parts: list[str] = []
        result_meta: dict[str, Any] = {}

        async def _run() -> None:
            async for msg in query(prompt=user_prompt, options=options):
                if isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        if isinstance(block, TextBlock):
                            transcript_parts.append(block.text)
                elif isinstance(msg, ResultMessage):
                    # Capture cost/usage metadata if the SDK provides it
                    for attr in ("total_cost_usd", "duration_ms", "num_turns"):
                        val = getattr(msg, attr, None)
                        if val is not None:
                            result_meta[attr] = val

        try:
            await asyncio.wait_for(_run(), timeout=request.timeout_s)
        except asyncio.TimeoutError:
            return DispatchResult(
                formula_id=request.formula_id,
                status="timeout",
                error=f"timed out after {request.timeout_s}s",
                dispatcher_name=self.name,
                latency_ms=int((time.monotonic() - t0) * 1000),
                raw_transcript="\n".join(transcript_parts) or None,
            )
        except Exception as exc:
            logger.exception("claude-sdk dispatch failed")
            return DispatchResult(
                formula_id=request.formula_id,
                status="error",
                error=f"{type(exc).__name__}: {exc}",
                dispatcher_name=self.name,
                latency_ms=int((time.monotonic() - t0) * 1000),
                raw_transcript="\n".join(transcript_parts) or None,
            )

        transcript = "\n".join(transcript_parts)
        output_json = _extract_json_block(transcript)
        if result_meta:
            output_json.setdefault("_meta", {}).update(result_meta)

        return DispatchResult(
            formula_id=request.formula_id,
            status="ok" if output_json else "error",
            output_json=output_json,
            latency_ms=int((time.monotonic() - t0) * 1000),
            dispatcher_name=self.name,
            error=None if output_json else "no JSON block found in agent output",
            raw_transcript=transcript,
        )


# ---------------------------------------------------------------------------
# Factory — imported by core/thinking_os/dispatcher.py via importlib
# ---------------------------------------------------------------------------

def build_dispatcher() -> ClaudeSDKDispatcher:
    """Entry point the factory looks for when loading this module."""
    return ClaudeSDKDispatcher()
