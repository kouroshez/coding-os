"""
Coding OS — Claude-SDK dispatcher (adapters/claude).

PURPOSE:      Real formula-agent spawning for Claude sessions via the
              official claude-agent-sdk. Translates DispatchRequest →
              ClaudeAgentOptions, runs the agent, and collects text blocks
              into a DispatchResult. Enables Phase M formula-roles to
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
import time
from pathlib import Path
from typing import Any

from thinking_os.dispatcher import DispatchRequest, DispatchResult
from thinking_os.dispatcher_helpers import extract_json_block, load_agent_prompt

logger = logging.getLogger("coding_os.dispatcher.claude_sdk")


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

def _presence_write(project_root: Path, agent: str, session_id: str,
                    event: str, pid: int | None = None) -> None:
    """Write a single presence event for an SDK-spawned sub-agent.

    PURPOSE: Formula sub-agents run as in-process SDK sessions, not via
             Claude Code's hook pipeline, so they never fire
             agent-presence.sh.  Writing presence directly from the
             dispatcher keeps the board's 3-state panel honest: a
             formula executing for 20s shows up as ACTIVE for that window.
    INPUT:   project_root, agent key, session id, lifecycle event
             ("start" / "tool" / "stop" / "end"), optional pid.
    OUTPUT:  $COS_STATE_DIR/<agent>/sessions/<session_id>.json
             (same schema as core/hooks/agent-presence.sh).
    DEPENDENCIES: json, os, pathlib, time.
    NOTES:   Fail-open — any error is silently logged; presence is a
             UX signal, not a correctness boundary.
    """
    import json as _json
    import os as _os
    import time as _time

    try:
        d = project_root / ".coding-os" / agent / "sessions"
        d.mkdir(parents=True, exist_ok=True)
        path = d / f"{session_id}.json"
        prev: dict[str, Any] = {}
        if path.exists():
            try:
                prev = _json.loads(path.read_text(encoding="utf-8"))
            except (OSError, _json.JSONDecodeError):
                prev = {}
        now = int(_time.time())
        new = {
            "agent": agent,
            "session_id": session_id,
            "pid": int(pid) if pid is not None else int(prev.get("pid") or _os.getpid()),
            "started_at": prev.get("started_at"),
            "last_prompt_at": prev.get("last_prompt_at"),
            "last_tool_at": prev.get("last_tool_at"),
            "last_stop_at": prev.get("last_stop_at"),
            "ended_at": prev.get("ended_at"),
        }
        if event == "start":
            new["started_at"] = now
            new["ended_at"] = None
            new["last_stop_at"] = None
        elif event == "tool":
            new["last_tool_at"] = now
            new["started_at"] = new["started_at"] or now
        elif event == "stop":
            new["last_stop_at"] = now
        elif event == "end":
            new["ended_at"] = now
        tmp = path.with_suffix(f".tmp.{_os.getpid()}")
        tmp.write_text(_json.dumps(new, separators=(",", ":")), encoding="utf-8")
        _os.replace(tmp, path)
    except OSError as exc:
        logger.debug("SDK presence write failed for %s: %s", session_id, exc)


class ClaudeSDKDispatcher:
    """
    PURPOSE:      Spawn a formula-agent as a real Claude Code sub-session
                  via claude-agent-sdk.query().
    NOTES:        available() returns False if the SDK import fails, so the
                  factory transparently falls back to the default dispatcher.
                  Each dispatch writes presence events so the board panel
                  reflects sub-agents that are actively producing output.
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
            system_prompt_body, _meta = load_agent_prompt(request.agent_file)
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

        # Presence bookkeeping — so the board's live-agents panel reflects
        # sub-agents that are actively generating, not just the host session.
        # cwd + formula id uniquely identify each dispatch.  formula_id is
        # already constrained by DispatchRequest._formula_id_is_safe, but
        # we sanitize again here: this module is a public extension point
        # any alternative runner could import and call, so never trust the
        # string we're about to drop into a path.
        import os as _os
        safe_formula = re.sub(r"[^A-Za-z0-9_-]", "_", request.formula_id) or "formula"
        sub_session_id = (
            f"ses-claude-sdk-{safe_formula}-{int(time.time())}-{_os.getpid()}"
        )
        project_root = Path(request.cwd) if request.cwd else Path(_os.getcwd())
        _presence_write(project_root, "claude", sub_session_id, "start")

        async def _run() -> None:
            async for msg in query(prompt=user_prompt, options=options):
                if isinstance(msg, AssistantMessage):
                    _presence_write(project_root, "claude", sub_session_id, "tool")
                    for block in msg.content:
                        if isinstance(block, TextBlock):
                            transcript_parts.append(block.text)
                elif isinstance(msg, ResultMessage):
                    # Capture cost/usage metadata if the SDK provides it
                    for attr in ("total_cost_usd", "duration_ms", "num_turns"):
                        val = getattr(msg, attr, None)
                        if val is not None:
                            result_meta[attr] = val

        # Single-writer for the terminal presence event so a future
        # side-effect (emit a stream event, decrement a gauge) can't
        # double-fire.  Happy path calls "stop" then finally emits "end";
        # error/timeout paths skip straight to "end".
        dispatch_outcome: DispatchResult | None = None
        try:
            try:
                await asyncio.wait_for(_run(), timeout=request.timeout_s)
                _presence_write(project_root, "claude", sub_session_id, "stop")
            except asyncio.TimeoutError:
                dispatch_outcome = DispatchResult(
                    formula_id=request.formula_id,
                    status="timeout",
                    error=f"timed out after {request.timeout_s}s",
                    dispatcher_name=self.name,
                    latency_ms=int((time.monotonic() - t0) * 1000),
                    raw_transcript="\n".join(transcript_parts) or None,
                )
            except Exception as exc:
                logger.exception("claude-sdk dispatch failed")
                dispatch_outcome = DispatchResult(
                    formula_id=request.formula_id,
                    status="error",
                    error=f"{type(exc).__name__}: {exc}",
                    dispatcher_name=self.name,
                    latency_ms=int((time.monotonic() - t0) * 1000),
                    raw_transcript="\n".join(transcript_parts) or None,
                )
        finally:
            _presence_write(project_root, "claude", sub_session_id, "end")

        if dispatch_outcome is not None:
            return dispatch_outcome

        transcript = "\n".join(transcript_parts)
        output_json = extract_json_block(transcript)
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
