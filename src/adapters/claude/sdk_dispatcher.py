"""Coding OS — Claude-SDK dispatcher (adapters/claude)."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any

from thinking_os.dispatcher import DispatchRequest, DispatchResult
from thinking_os.dispatcher_helpers import extract_json_block, load_agent_prompt

logger = logging.getLogger("coding_os.dispatcher.claude_sdk")

# Models that require special effort handling. Opus 4.7 needs the highest
# effort level available; Py SDK 0.1.73 caps at "max" (no "xhigh" yet).
_OPUS_47_MODEL_IDS = ("claude-opus-4-7", "claude-opus-4-7-20260101")

# Default MCP allow-list pattern. coding-os exposes ~60 cos_* tools via
# the central FastMCP server registered at .mcp.json::mcpServers.coding-os.
# `acceptEdits` and `default` permission modes do NOT auto-approve MCP,
# so we list them explicitly. Wildcard form per SDK docs §D.2.
_DEFAULT_COS_MCP_ALLOW = "mcp__coding-os__*"

# Destructive Bash patterns headless dispatch must never run. Hard-deny
# wins over allow rules even in bypassPermissions (digest §B.4 order),
# so this is defense-in-depth on top of permission_mode="dontAsk".
_DESTRUCTIVE_BASH_DENY = (
    "Bash(rm -rf:*)",
    "Bash(rm -fr:*)",
    "Bash(git push --force:*)",
    "Bash(git push -f:*)",
    "Bash(git reset --hard:*)",
    "Bash(git clean -f:*)",
    "Bash(sudo:*)",
    "Bash(curl * | bash:*)",
    "Bash(curl * | sh:*)",
    "Bash(wget * | bash:*)",
    "Bash(wget * | sh:*)",
)

# OTEL env vars the dispatcher copies from the parent process so the
# sub-session emits to the same collector. No collector defaults are
# bundled (D5) — operator sets exporter / endpoint / headers.
_OTEL_FORWARDED_VARS = (
    "OTEL_TRACES_EXPORTER",
    "OTEL_METRICS_EXPORTER",
    "OTEL_LOGS_EXPORTER",
    "OTEL_EXPORTER_OTLP_PROTOCOL",
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "OTEL_EXPORTER_OTLP_HEADERS",
    "OTEL_RESOURCE_ATTRIBUTES",
    "OTEL_METRIC_EXPORT_INTERVAL",
    "OTEL_LOGS_EXPORT_INTERVAL",
    "OTEL_TRACES_EXPORT_INTERVAL",
    "OTEL_LOG_USER_PROMPTS",
    "OTEL_LOG_TOOL_DETAILS",
    "OTEL_LOG_TOOL_CONTENT",
    "OTEL_LOG_RAW_API_BODIES",
    "ENABLE_BETA_TRACING_DETAILED",
    "BETA_TRACING_ENDPOINT",
    "CLAUDE_CODE_ENABLE_TELEMETRY",
    "CLAUDE_CODE_ENHANCED_TELEMETRY_BETA",
)


def _resolve_output_schema(meta: dict[str, Any]) -> dict[str, Any] | None:
    raw = meta.get("output_schema") if isinstance(meta, dict) else None
    if not isinstance(raw, str) or not raw.strip():
        return None
    cls_name = raw.split(".")[-1].strip()
    if not cls_name.isidentifier():
        logger.warning("invalid output_schema reference %r — ignoring", raw)
        return None
    try:
        from thinking_os import cognition_schemas as _schemas
    except ImportError as exc:
        logger.warning("cognition_schemas import failed: %s", exc)
        return None
    schema_cls = getattr(_schemas, cls_name, None)
    if schema_cls is None or not hasattr(schema_cls, "model_json_schema"):
        logger.warning("no Pydantic class %s in cognition_schemas", cls_name)
        return None
    try:
        return schema_cls.model_json_schema()
    except (TypeError, ValueError) as exc:
        logger.warning("model_json_schema() failed for %s: %s", cls_name, exc)
        return None


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


def _presence_write(
    project_root: Path, agent: str, session_id: str, event: str, pid: int | None = None
) -> None:
    """Write a single presence event for an SDK-spawned sub-agent."""
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
            )

        # Skill inheritance — formula sub-sessions get a fresh context, so
        # they don't inherit parent skills. Each role's frontmatter
        # declares which skills it needs (e.g. implementer → ["clean-code"]).
        # Other adapters that don't honor this key ignore it (Rule 1).
        role_skills = agent_meta.get("skills") if isinstance(agent_meta, dict) else None
        if role_skills is not None and (
            not isinstance(role_skills, list) or not all(isinstance(s, str) for s in role_skills)
        ):
            role_skills = None
            logger.warning(
                "agent file %s has invalid `skills` frontmatter — ignoring",
                request.agent_file,
            )

        # Append the formula spec to Claude Code's preset prompt. The
        # preset carries Claude Code's coding/safety baseline; the formula
        # body adds the role-specific Output contract. Setting
        # `exclude_dynamic_sections=True` strips per-cwd state (git,
        # date, OS, memory paths) from the system prompt and emits it as
        # a first-user-message block instead — this is what makes the
        # prompt cache reusable across consumer projects.
        formula_append = (
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
        system_prompt: dict[str, Any] = {
            "type": "preset",
            "preset": "claude_code",
            "append": formula_append,
            "exclude_dynamic_sections": True,
        }
        user_prompt = (
            f"Input slice (upstream formulas only):\n"
            f"```json\n{json.dumps(request.input_slice, indent=2, default=str)}\n```\n\n"
            f"{request.prompt}"
        )

        # Always include the coding-os MCP wildcard alongside any caller-
        # provided allow-list. `acceptEdits` does NOT auto-approve MCP,
        # so without an explicit entry every cos_* tool call would deny
        # in dontAsk mode.
        allow_list = list(request.allowed_tools or [])
        if not any(item.startswith("mcp__coding-os") for item in allow_list):
            allow_list.append(_DEFAULT_COS_MCP_ALLOW)

        # Opus 4.7 needs the top effort level available. Py SDK 0.1.73
        # tops out at "max"; "xhigh" exists only on the TS side as of
        # 2026-05-04. Re-evaluate when SDK lifts the cap.
        effort: str | None = None
        if request.model in _OPUS_47_MODEL_IDS:
            effort = "max"

        # Structured output (T1) — opt-in per role via
        # `structured_output: true` frontmatter. SDK enforces the
        # schema and surfaces failures as
        # subtype="error_max_structured_output_retries".
        output_format: dict[str, Any] | None = None
        wants_structured = bool(
            isinstance(agent_meta, dict) and agent_meta.get("structured_output")
        )
        if wants_structured:
            schema = _resolve_output_schema(agent_meta)
            if schema is not None:
                output_format = {"type": "json_schema", "schema": schema}
            else:
                logger.warning(
                    "role %s requested structured_output but schema could not be "
                    "resolved — falling back to regex extraction",
                    request.formula_id,
                )

        # Forward telemetry env so the sub-session emits to the same
        # OTEL collector as the parent (D5 leaves the collector to
        # operators; we just propagate). OTEL_SERVICE_NAME identifies
        # the dispatcher distinctly from a normal claude-code session.
        env: dict[str, str] = {}
        for var in _OTEL_FORWARDED_VARS:
            value = os.environ.get(var)
            if value:
                env[var] = value
        env.setdefault("OTEL_SERVICE_NAME", "coding-os-claude")
        env.setdefault("OTEL_METRICS_INCLUDE_SESSION_ID", "true")

        # Long-context beta (D6). Caller opts in per request; default
        # short context to keep cache hits high and cost predictable.
        betas = ["context-1m-2025-08-07"] if request.long_context else None

        logger.debug(
            "claude-sdk dispatch: formula=%s model=%s effort=%s "
            "structured=%s budget_usd=%s tools=%s",
            request.formula_id,
            request.model,
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
        result_meta: dict[str, Any] = {"model": request.model} if request.model else {}
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
        max_turns = 3 if output_format is not None else 1
        opts_kwargs: dict[str, Any] = dict(
            system_prompt=system_prompt,
            max_turns=max_turns,
            allowed_tools=allow_list,
            disallowed_tools=list(_DESTRUCTIVE_BASH_DENY),
            cwd=request.cwd,
            # Headless dispatch: never prompt the user. Allow-list is the
            # contract; unmatched tools deny silently.
            permission_mode="dontAsk",
            # Isolate from the host user's ~/.claude/. The formula sub-
            # session must be reproducible across machines — user
            # settings, memory, and CLAUDE.md outside the project root
            # would silently change behavior.
            setting_sources=["project"],
            model=request.model,
            effort=effort,
            # Per-role skill inheritance. Sub-sessions don't inherit
            # parent skills, so each role declares its required skills
            # in its agent file's frontmatter. None = use SDK default.
            skills=role_skills,
            env=env,
        )
        if output_format is not None:
            opts_kwargs["output_format"] = output_format
        if request.max_budget_usd is not None:
            opts_kwargs["max_budget_usd"] = float(request.max_budget_usd)
        if betas is not None:
            opts_kwargs["betas"] = betas
        # T7.1: pass the pre-computed session id so the SDK session key matches
        # the presence file key. Resumable via ClaudeAgentOptions(resume=...).
        opts_kwargs["session_id"] = sub_session_id
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

        async def _run() -> None:
            nonlocal result_subtype, structured_output
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
                    for block in msg.content:
                        if isinstance(block, TextBlock):
                            transcript_parts.append(block.text)
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

        transcript = "\n".join(transcript_parts)
        latency_ms = int((time.monotonic() - t0) * 1000)

        # Map SDK error subtypes to dispatcher status. Budget exhaustion
        # and retry exhaustion are operationally distinct from a generic
        # "error_during_execution" — keep the original subtype in the
        # error string so callers can pattern-match.
        if result_subtype == "error_max_budget_usd":
            return DispatchResult(
                formula_id=request.formula_id,
                status="error",
                error=(
                    f"max_budget_usd={request.max_budget_usd} exhausted; "
                    f"actual_cost_usd={result_meta.get('total_cost_usd')!r}"
                ),
                output_json={"_meta": dict(result_meta)},
                latency_ms=latency_ms,
                dispatcher_name=self.name,
                raw_transcript=transcript or None,
            )
        if result_subtype == "error_max_turns":
            return DispatchResult(
                formula_id=request.formula_id,
                status="error",
                error="max_turns exhausted",
                output_json={"_meta": dict(result_meta)},
                latency_ms=latency_ms,
                dispatcher_name=self.name,
                raw_transcript=transcript or None,
            )
        if result_subtype == "error_max_structured_output_retries":
            # Schema enforcement gave up; fall through to regex extraction
            # so the dispatcher still surfaces partial work instead of an
            # opaque error. Caller sees the subtype via raw_transcript +
            # output_json._meta.subtype.
            result_meta["structured_output_retry_exhausted"] = True

        # Prefer SDK-enforced structured output. extract_json_block is the
        # 0.1.x fallback for roles that don't opt into structured output
        # AND for retry-exhausted runs (logged above).
        output_json: dict[str, Any]
        if isinstance(structured_output, dict):
            output_json = dict(structured_output)
        else:
            output_json = extract_json_block(transcript)

        if result_meta:
            output_json.setdefault("_meta", {}).update(result_meta)
        if result_subtype:
            output_json.setdefault("_meta", {})["subtype"] = result_subtype

        ok = bool(output_json) and any(k != "_meta" for k in output_json.keys())
        # T1.5: surface the retry-exhausted subtype in the error field so callers
        # can route to a retry-with-relaxed-prompt path. Status stays "ok" when
        # regex fallback recovered usable JSON — the output bundle is still
        # populated. Callers that need strict schema compliance should check error.
        if not ok:
            error_str = "no usable JSON in dispatch output"
        elif result_subtype == "error_max_structured_output_retries":
            error_str = (
                "error_max_structured_output_retries: schema enforcement exhausted, "
                "fell back to regex extraction"
            )
        else:
            error_str = None
        return DispatchResult(
            formula_id=request.formula_id,
            status="ok" if ok else "error",
            output_json=output_json,
            latency_ms=latency_ms,
            dispatcher_name=self.name,
            error=error_str,
            raw_transcript=transcript,
        )


# ---------------------------------------------------------------------------
# Factory — imported by core/thinking_os/dispatcher.py via importlib
# ---------------------------------------------------------------------------


def build_dispatcher() -> ClaudeSDKDispatcher:
    """Entry point the factory looks for when loading this module."""
    return ClaudeSDKDispatcher()
