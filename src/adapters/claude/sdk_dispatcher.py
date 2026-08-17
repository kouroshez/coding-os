"""Coding OS — Claude-SDK dispatcher (adapters/claude).

Module layout:
  _claude_sdk_options    tool floors, model aliases, auth env, ClaudeAgentOptions
  _claude_sdk_telemetry  presence files + cognition-trace events
  _claude_sdk_result     error taxonomy + the terminal DispatchResult mapping
  this module            the dispatch loop that drives the SDK query stream

Loaded two ways: as `adapters.claude.sdk_dispatcher` when the wheel is on the
path, and by file path via `spec_from_file_location` by the dispatcher factory
and the Hub chat route. The second identity has no parent package, so the
siblings resolve through this directory on `sys.path` rather than a relative
import.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import sys
import time
import uuid
from pathlib import Path
from typing import Any

from thinking_os.dispatcher import DispatchRequest, DispatchResult
from thinking_os.dispatcher_helpers import load_agent_prompt

if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.append(str(Path(__file__).resolve().parent))

from _claude_sdk_options import (
    _CHAT_BASE_TOOLS as _CHAT_BASE_TOOLS,
    _CHAT_PROFILES as _CHAT_PROFILES,
    _DEFAULT_COS_MCP_ALLOW as _DEFAULT_COS_MCP_ALLOW,
    _DESTRUCTIVE_BASH_DENY as _DESTRUCTIVE_BASH_DENY,
    _OTEL_FORWARDED_VARS as _OTEL_FORWARDED_VARS,
    _XHIGH_EFFORT_MODEL_PREFIXES as _XHIGH_EFFORT_MODEL_PREFIXES,
    _claude_auth_env as _claude_auth_env,
    _cos_mcp_servers as _cos_mcp_servers,
    _dispatch_env as _dispatch_env,
    _formula_prompts as _formula_prompts,
    _hub_settings_path as _hub_settings_path,
    _resolve_model_alias as _resolve_model_alias,
    _resolve_output_schema as _resolve_output_schema,
    _structured_output_format as _structured_output_format,
    _validated_role_skills as _validated_role_skills,
    claude_agent_options as claude_agent_options,
    claude_session_options as claude_session_options,
)
from _claude_sdk_result import (
    _failure_fields as _failure_fields,
    _finalize_dispatch_result as _finalize_dispatch_result,
)
from _claude_sdk_telemetry import (
    _dispatch_trace_content_enabled as _dispatch_trace_content_enabled,
    _emit_dispatch_trace as _emit_dispatch_trace,
    _presence_write as _presence_write,
)

logger = logging.getLogger("coding_os.dispatcher.claude_sdk")

# Tool call + tool result + closing assistant message. A role that reads one file
# before answering needs all three, whether or not it returns a typed payload.
_DEFAULT_MAX_TURNS = 3


class ClaudeSDKDispatcher:
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
                **_failure_fields(
                    "error", f"claude-agent-sdk not importable: {self._import_error}"
                ),
            )

        from claude_agent_sdk import (
            AssistantMessage,
            ClaudeAgentOptions,
            HookMatcher,
            ResultMessage,
            TextBlock,
            UserMessage,
            query,
        )

        # SDK searches cwd if agent_file is relative — silently picks the
        # wrong file if a same-named role lives in another path. Force
        # absolute so a misconfigured caller fails loudly here, not 30s
        # into a wrong dispatch.
        if not Path(request.agent_file).is_absolute():
            return DispatchResult(
                formula_id=request.formula_id,
                status="error",
                error=f"agent_file must be absolute, got: {request.agent_file!r}",
                dispatcher_name=self.name,
                latency_ms=int((time.monotonic() - t0) * 1000),
                **_failure_fields(
                    "error", f"agent_file must be absolute, got: {request.agent_file!r}"
                ),
            )

        try:
            system_prompt_body, agent_meta = load_agent_prompt(request.agent_file)
        except FileNotFoundError as exc:
            return DispatchResult(
                formula_id=request.formula_id,
                status="error",
                error=str(exc),
                dispatcher_name=self.name,
                latency_ms=int((time.monotonic() - t0) * 1000),
                **_failure_fields("error", str(exc)),
            )

        role_skills = _validated_role_skills(agent_meta, request.agent_file)
        system_prompt, user_prompt = _formula_prompts(request, system_prompt_body)

        # Always include the coding-os MCP wildcard alongside any caller-
        # provided allow-list. `acceptEdits` does NOT auto-approve MCP,
        # so without an explicit entry every cos_* tool call would deny
        # in dontAsk mode.
        allow_list = list(request.allowed_tools or [])
        if not any(item.startswith("mcp__coding-os") for item in allow_list):
            allow_list.append(_DEFAULT_COS_MCP_ALLOW)

        # Resolve a routed tier alias (sonnet/opus/...) to a concrete adapter
        # model id BEFORE it reaches the SDK or the effort gate (R10/F6).
        resolved_model = _resolve_model_alias(request.model)

        # High-tier models get "xhigh"; everything else uses the SDK
        # default (None → "high"). See _XHIGH_EFFORT_MODEL_PREFIXES.
        effort: str | None = request.effort
        if resolved_model and resolved_model.startswith(_XHIGH_EFFORT_MODEL_PREFIXES):
            effort = effort or "xhigh"

        output_format = _structured_output_format(agent_meta, request.formula_id)
        env = _dispatch_env(request.cwd or os.getcwd())

        # Long-context beta (D6). Caller opts in per request; default
        # short context to keep cache hits high and cost predictable.
        betas = ["context-1m-2025-08-07"] if request.long_context else None

        logger.debug(
            "claude-sdk dispatch: formula=%s model=%s effort=%s "
            "structured=%s budget_usd=%s tools=%s",
            request.formula_id,
            resolved_model,
            effort,
            bool(output_format),
            request.max_budget_usd,
            allow_list,
        )

        # Pre-compute sub-session identity so programmatic hook closures
        # below can stamp presence updates with a stable id. Same path
        # safety as the existing presence_write call (formula_id already
        # restricted to [A-Za-z0-9_-] by DispatchRequest validator).
        safe_formula = re.sub(r"[^A-Za-z0-9_-]", "_", request.formula_id) or "formula"
        sub_session_id = f"ses-claude-sdk-{safe_formula}-{int(time.time())}-{os.getpid()}"
        project_root = Path(request.cwd) if request.cwd else Path(os.getcwd())

        # Per-dispatch state captured by programmatic hooks (T3.1, T3.2)
        # and by the message-stream handler (T3.3 / T1.3). Closures
        # below bind to these locals so concurrent dispatches stay
        # isolated.
        transcript_parts: list[str] = []
        # v27: capture the model the dispatcher requested so persistence
        # can fill formula_dispatches.model without re-deriving from usage.
        result_meta: dict[str, Any] = {"model": resolved_model} if resolved_model else {}
        result_subtype: str | None = None
        structured_output: Any = None
        tool_calls: list[dict[str, Any]] = []
        tool_failures: list[dict[str, Any]] = []
        # T9.2 — UserMessage UUIDs for file checkpointing replay
        checkpoint_uuids: list[str] = []

        # Hook callbacks must NEVER raise — the SDK propagates exceptions
        # back to the CLI subprocess which exits 1, killing the dispatch.
        # Wrap every body in try/except + log; always return `{}` so the
        # SDK keeps streaming.
        async def _pre_tool_use(
            input_data: dict[str, Any],
            tool_use_id: str | None,
            _ctx: Any,
        ) -> dict[str, Any]:
            try:
                tool_calls.append(
                    {
                        "tool_use_id": tool_use_id,
                        "tool_name": input_data.get("tool_name"),
                        "tool_input": input_data.get("tool_input"),
                    }
                )
            except Exception as exc:
                logger.debug("PreToolUse hook capture failed: %s", exc)
            return {}

        async def _post_tool_use_failure(
            input_data: dict[str, Any],
            tool_use_id: str | None,
            _ctx: Any,
        ) -> dict[str, Any]:
            try:
                tool_failures.append(
                    {
                        "tool_use_id": tool_use_id,
                        "tool_name": input_data.get("tool_name"),
                        "tool_response": input_data.get("tool_response"),
                    }
                )
                logger.warning(
                    "claude-sdk dispatch tool failure: formula=%s tool=%s",
                    request.formula_id,
                    input_data.get("tool_name"),
                )
            except Exception as exc:
                logger.debug("PostToolUseFailure hook capture failed: %s", exc)
            return {}

        # `--json-schema` activates a `StructuredOutput` tool the model
        # invokes to deliver the typed payload. That tool call AND the
        # tool_result it produces each burn a turn, plus the model
        # often emits a closing assistant turn after the result. Using
        # 3 turns avoids spurious `error_max_turns` subtypes when the
        # model decides to acknowledge before stopping. Even then the
        # post-stream handler treats a populated `structured_output`
        # as success regardless of subtype.
        #
        # The free-text branch used to get 1, which is not a budget — it is a
        # guaranteed failure. A role with a tools_budget spends its first turn
        # calling a tool and has nothing left for the answer, so all ten roles
        # that do not declare `structured_output` returned
        # `error_max_turns` on every dispatch. Both branches now get the same
        # floor: the reasoning written above for the structured path (tool call,
        # tool result, closing message) applies verbatim to a role that reads a
        # file before answering.
        max_turns = request.max_turns if request.max_turns is not None else _DEFAULT_MAX_TURNS
        opts_kwargs: dict[str, Any] = {
            "system_prompt": system_prompt,
            "max_turns": max_turns,
            "allowed_tools": allow_list,
            "disallowed_tools": list(_DESTRUCTIVE_BASH_DENY),
            "cwd": request.cwd,
            # Headless dispatch: never prompt the user. Allow-list is the
            # contract; unmatched tools deny silently.
            "permission_mode": "dontAsk",
            # Isolate from the host user's ~/.claude/. The formula sub-
            # session must be reproducible across machines — user
            # settings, memory, and CLAUDE.md outside the project root
            # would silently change behavior.
            "setting_sources": ["project"],
            "model": resolved_model,
            "effort": effort,
            # Per-role skill inheritance. Sub-sessions don't inherit
            # parent skills, so each role declares its required skills
            # in its agent file's frontmatter. None = use SDK default.
            "skills": role_skills,
            "env": env,
        }
        if output_format is not None:
            opts_kwargs["output_format"] = output_format
        if request.max_budget_usd is not None:
            opts_kwargs["max_budget_usd"] = float(request.max_budget_usd)
        if betas is not None:
            opts_kwargs["betas"] = betas
        # The CLI validates --session-id as a UUID, so the SDK gets a real
        # UUID while presence/trace keys keep the readable sub_session_id;
        # result_meta carries the mapping for resume debugging.
        sdk_session_uuid = str(uuid.uuid4())
        opts_kwargs["session_id"] = sdk_session_uuid
        result_meta["sdk_session_id"] = sdk_session_uuid
        # T9.1: enable file checkpointing for roles that declare it in frontmatter.
        # Implements checkpoint/replay for edit-heavy roles (implementer/refactorer).
        if isinstance(agent_meta, dict) and agent_meta.get("enable_file_checkpointing"):
            opts_kwargs["enable_file_checkpointing"] = True
        # Programmatic hooks (T3) — these run inline in the
        # dispatcher process, capturing tool call metadata and failures
        # for the formula_dispatches audit row. Empty matcher = match
        # every tool. PostToolUseFailure surfaces tool errors that the
        # SDK would otherwise swallow into the transcript.
        # T3.4 [-]: SubagentStart / SubagentStop not wired here — D1
        # chose query() over Agent-tool, so no sub-agents are spawned.
        # These events still fire in interactive sessions via registry.yaml.
        opts_kwargs["hooks"] = {
            "PreToolUse": [HookMatcher(matcher="", hooks=[_pre_tool_use])],
            "PostToolUseFailure": [HookMatcher(matcher="", hooks=[_post_tool_use_failure])],
        }
        options = ClaudeAgentOptions(**opts_kwargs)

        # Presence: mark "start" only after options is built so the
        # board doesn't show a session that never actually launched
        # (e.g. ClaudeAgentOptions raised). The matching "end" emits
        # in the finally block below.
        _presence_write(project_root, "claude", sub_session_id, "start")
        _emit_dispatch_trace(
            sub_session_id,
            "dispatch_started",
            request.formula_id,
            {"formula_id": request.formula_id},
        )

        dispatch_turn_seq = 0

        async def _run() -> None:
            nonlocal result_subtype, structured_output, dispatch_turn_seq
            async for msg in query(prompt=user_prompt, options=options):
                if isinstance(msg, UserMessage):
                    # Capture checkpoint UUIDs for file-checkpointing replay (T9.2)
                    try:
                        uuid_val = getattr(msg, "uuid", None)
                        if uuid_val is not None:
                            checkpoint_uuids.append(str(uuid_val))
                    except Exception as exc:
                        logger.debug("UUID capture failed: %s", exc)
                elif isinstance(msg, AssistantMessage):
                    _presence_write(project_root, "claude", sub_session_id, "tool")
                    _turn_texts: list[str] = []
                    for block in msg.content:
                        if isinstance(block, TextBlock):
                            transcript_parts.append(block.text)
                            _turn_texts.append(block.text)
                    # Count + emit only text-bearing turns so `turns` tracks
                    # reply turns (tool-only assistant messages are captured
                    # separately in result_meta['tool_calls']); a pure tool
                    # turn otherwise inflated the count with a chars=0 event.
                    if _turn_texts:
                        dispatch_turn_seq += 1
                        _turn_data: dict[str, Any] = {
                            "seq": dispatch_turn_seq,
                            "chars": sum(len(t) for t in _turn_texts),
                        }
                        if _dispatch_trace_content_enabled():
                            _turn_data["text"] = "".join(_turn_texts)
                        _emit_dispatch_trace(
                            sub_session_id, "dispatch_turn", request.formula_id, _turn_data
                        )
                elif isinstance(msg, ResultMessage):
                    # ResultMessage is emitted once per query, at the
                    # end. Capture every field the post-stream handler
                    # might need.
                    result_subtype = getattr(msg, "subtype", None)
                    structured_output = getattr(msg, "structured_output", None)
                    for attr in (
                        "total_cost_usd",
                        "duration_ms",
                        "duration_api_ms",
                        "num_turns",
                        "stop_reason",
                        "session_id",
                    ):
                        val = getattr(msg, attr, None)
                        if val is not None:
                            result_meta[attr] = val
                    # usage / model_usage carry the per-step token
                    # breakdown (input, output, cache_read,
                    # cache_creation). Persist verbatim — caller
                    # decides whether to summarize.
                    for attr in ("usage", "model_usage", "permission_denials"):
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
                    **_failure_fields("timeout", f"timed out after {request.timeout_s}s"),
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
                    **_failure_fields("error", f"{type(exc).__name__}: {exc}"),
                )
        finally:
            _presence_write(project_root, "claude", sub_session_id, "end")
            # Derive the terminal status from what is known here: an early
            # timeout/error sets dispatch_outcome; otherwise only the budget /
            # max-turns subtypes become a status="error" DispatchResult below —
            # error_max_structured_output_retries is recoverable (it falls
            # through to regex extraction and can still return "ok"), so match
            # those two exactly rather than any "error"-prefixed subtype.
            if dispatch_outcome is not None:
                _final_status = dispatch_outcome.status
            elif result_subtype in ("error_max_budget_usd", "error_max_turns"):
                _final_status = "error"
            else:
                _final_status = "ok"
            _emit_dispatch_trace(
                sub_session_id,
                "dispatch_completed",
                request.formula_id,
                {"status": _final_status, "turns": dispatch_turn_seq},
            )

        # Programmatic-hook captures ride into result_meta so the
        # `formula_dispatches` audit row records full tool history.
        if tool_calls:
            result_meta["tool_calls"] = tool_calls
        if tool_failures:
            result_meta["tool_failures"] = tool_failures
        # T9.2: file-checkpointing replay UUIDs (only populated when
        # enable_file_checkpointing is set in role frontmatter).
        if checkpoint_uuids:
            result_meta["checkpoints"] = checkpoint_uuids

        if dispatch_outcome is not None:
            return dispatch_outcome

        return _finalize_dispatch_result(
            request,
            dispatcher_name=self.name,
            result_subtype=result_subtype,
            result_meta=result_meta,
            structured_output=structured_output,
            transcript="\n".join(transcript_parts),
            latency_ms=int((time.monotonic() - t0) * 1000),
        )


# ---------------------------------------------------------------------------
# Factory — imported by core/thinking_os/dispatcher.py via importlib
# ---------------------------------------------------------------------------


def build_dispatcher() -> ClaudeSDKDispatcher:
    """Entry point the factory looks for when loading this module."""
    return ClaudeSDKDispatcher()
