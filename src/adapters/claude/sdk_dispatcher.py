"""Coding OS — Claude-SDK dispatcher (adapters/claude)."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any

from thinking_os.dispatcher import DispatchRequest, DispatchResult
from thinking_os.dispatcher_helpers import extract_json_block, load_agent_prompt

logger = logging.getLogger("coding_os.dispatcher.claude_sdk")

# High-tier reasoning models (Fable 5, Opus 4.8/4.7) take the "xhigh"
# effort level — the best setting for coding/agentic work and the Claude
# Code default. "xhigh" is available in the Py SDK since 0.1.74 (it was
# TS-only before) and falls back to "high" on models that don't support
# it. Prefix-matched so dated snapshots (…-20260101) are covered too.
_XHIGH_EFFORT_MODEL_PREFIXES = (
    "claude-fable-5",
    "claude-opus-4-8",
    "claude-opus-4-7",
)

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

# Base tool allow-list for the interactive Hub-chat surface. The Claude CLI
# treats --allowedTools as an EXCLUSIVE allow-list under permission_mode=
# "dontAsk" (verified live: listing only the MCP wildcard denies Read), so
# the chat profile must enumerate the base tools it keeps. Write/Edit/
# MultiEdit are intentionally absent — chat is read+research+MCP and must
# not mutate code (closes the dogfood-corruption gap by construction).
_CHAT_BASE_TOOLS = (
    "Read",
    "Grep",
    "Glob",
    "Bash",
    "WebFetch",
    "WebSearch",
    "TodoWrite",
)

_CHAT_PROFILES = ("chat", "chat_resume")


def _failure_fields(status: str, error: str | None) -> dict[str, Any]:
    if status == "ok":
        return {}
    message = (error or "").lower()
    if status == "timeout":
        return {"error_category": "timeout", "retryable": True, "outcome": "unknown"}
    retry_after: int | None = None
    match = re.search(r"(?:retry after|try again in)\s+(\d+)\s*(?:seconds?|s)?", message)
    if match:
        retry_after = int(match.group(1))
    if any(
        token in message
        for token in ("rate limit", "usage limit", "quota", "too many requests", "429", "capacity")
    ):
        return {
            "error_category": "capacity",
            "retryable": True,
            "retry_after_s": retry_after,
            "outcome": "known_failed",
        }
    if any(
        token in message
        for token in ("unauthorized", "authentication", "not logged in", "401", "403")
    ):
        return {"error_category": "auth", "outcome": "known_failed"}
    # Provider-side overload (529) and internal errors (5xx) are NOT your quota,
    # so they must not open the capacity breaker — but they are the most
    # retryable class there is, and reporting them non-retryable is wrong.
    if any(token in message for token in ("overloaded", "529", "api_error", "500", "502", "503")):
        return {"error_category": "provider", "retryable": True, "outcome": "unknown"}
    if any(token in message for token in ("not importable", "not found")):
        return {"error_category": "unavailable", "outcome": "known_failed"}
    if any(token in message for token in ("must be absolute", "max_budget_usd", "max_turns")):
        return {"error_category": "invalid", "outcome": "known_failed"}
    return {"error_category": "provider", "outcome": "unknown"}


def _cos_mcp_servers(cwd: str) -> dict[str, Any]:
    try:
        data = json.loads((Path(cwd) / ".mcp.json").read_text(encoding="utf-8"))
        cos = (data.get("mcpServers") or {}).get("coding-os")
        return {"coding-os": cos} if cos else {}
    except (OSError, ValueError) as exc:
        logger.debug("cos mcp_servers unavailable for %s: %s", cwd, exc)
        return {}


_MODEL_ALIAS_CACHE: dict[str, str] = {}


# Map a tier alias (sonnet/opus/haiku) → a concrete adapter.yaml model id before
# it reaches the SDK: the kernel router speaks in tiers (claude-sdk.md — the
# adapter owns alias→id), so a routed 'sonnet' must become 'claude-sonnet-4-6'.
# `claude-*` ids and None pass through; an unknown non-id falls back to the
# adapter default so the SDK never receives a bare tier (R10/F6).
def _resolve_model_alias(model: str | None) -> str | None:
    if not model or model.startswith("claude-"):
        return model
    alias = model.strip().lower()
    if not alias:
        return model
    if alias in _MODEL_ALIAS_CACHE:
        return _MODEL_ALIAS_CACHE[alias]
    resolved = model
    try:
        import yaml

        data = (
            yaml.safe_load(
                (Path(__file__).resolve().parent / "adapter.yaml").read_text(encoding="utf-8")
            )
            or {}
        )
        models = [m for m in (data.get("models") or []) if isinstance(m, dict) and m.get("id")]
        match = next((str(m["id"]) for m in models if alias in str(m["id"]).lower()), None)
        if match is None:
            match = next((str(m["id"]) for m in models if m.get("default")), None)
            if match:
                logger.warning("unknown model alias %r → adapter default %s", model, match)
        if match:
            resolved = match
    except Exception as exc:
        logger.debug("model alias resolution skipped for %r: %s", model, exc)
    _MODEL_ALIAS_CACHE[alias] = resolved
    return resolved


def _hub_settings_path(cwd: str) -> Path:
    state_dir = os.environ.get("COS_STATE_DIR")
    if state_dir:
        return Path(state_dir) / "hub-settings.json"
    return Path(cwd or os.getcwd()) / ".coding-os" / "hub-settings.json"


# Deterministic auth-mode override (TASK-756): Hub Settings → Claude Auth lets a
# project pick "subscription" (default — the CLI's own OAuth session, byte-
# identical to before this existed) or "api_key" (forward the user's key as
# ANTHROPIC_API_KEY). Per platform.claude.com/docs/en/authentication, an API
# key set on the subprocess env beats subscription OAuth in non-interactive/SDK
# mode — so "subscription" mode must EXPLICITLY clear the var (not merely omit
# it), or a stray ANTHROPIC_API_KEY already in the Hub server's own shell would
# silently override the user's chosen mode. Always returns an override (never
# {} = no-op) so this is a real switch, not a best-effort hint.
def _claude_auth_env(cwd: str) -> dict[str, str]:
    try:
        data = json.loads(_hub_settings_path(cwd).read_text(encoding="utf-8"))
        auth = data.get("claude_auth") if isinstance(data, dict) else None
        if isinstance(auth, dict) and auth.get("mode") == "api_key":
            key = auth.get("api_key")
            if isinstance(key, str) and key:
                return {"ANTHROPIC_API_KEY": key}
    except (OSError, ValueError) as exc:
        logger.debug("claude_auth resolution skipped for cwd=%r: %s", cwd, exc)
    return {"ANTHROPIC_API_KEY": ""}


def claude_session_options(
    profile: str,
    *,
    cwd: str,
    model: str | None = None,
    system_prompt: Any = None,
    resume: str | None = None,
    fork: bool = False,
    effort: str | None = None,
):
    """Build ClaudeAgentOptions for a profile — the SSOT for Claude SDK sessions (docs/adapters/session-options-builder.md)."""
    from claude_agent_sdk import ClaudeAgentOptions

    if profile not in _CHAT_PROFILES:
        raise NotImplementedError(
            f"claude_session_options: profile {profile!r} not yet migrated (TASK-417 phases)"
        )

    model = _resolve_model_alias(model)  # tier alias → concrete id (R10/F6)
    opts: dict[str, Any] = {
        "cwd": cwd,
        "model": model,
        "permission_mode": "dontAsk",
        # Fast conversational surface: skip the ~40s project SessionStart hook
        # suite. Capability comes from programmatic mcp_servers below, NOT from
        # setting_sources, so cos_* works without that latency.
        "setting_sources": [],
        "include_partial_messages": True,
        # P2 capability: register coding-os MCP programmatically — renders
        # --mcp-config independent of setting_sources (subprocess_cli.py:307).
        "mcp_servers": _cos_mcp_servers(cwd),
        # Exclusive allow-list under dontAsk: base tools + the MCP wildcard.
        "allowed_tools": [*_CHAT_BASE_TOOLS, _DEFAULT_COS_MCP_ALLOW],
        # P3: destructive-Bash deny floor (rm -rf / force-push / sudo / pipe-to-sh).
        "disallowed_tools": list(_DESTRUCTIVE_BASH_DENY),
        # Hub Settings → Claude Auth (TASK-756): subscription OAuth by default,
        # ANTHROPIC_API_KEY when the project opted into api_key mode.
        "env": _claude_auth_env(cwd),
    }
    if system_prompt is not None:
        opts["system_prompt"] = system_prompt
    if effort:
        opts["effort"] = effort
    if profile == "chat_resume":
        if resume:
            opts["resume"] = resume
        opts["fork_session"] = fork
    return ClaudeAgentOptions(**opts)


def claude_agent_options(**kwargs: Any):
    """Generic ClaudeAgentOptions constructor — the adapter seam core routes every
    non-profile option build through (P8: core never constructs the SDK type itself)."""
    from claude_agent_sdk import ClaudeAgentOptions

    return ClaudeAgentOptions(**kwargs)


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
        # Schema parity with _helpers/presence_write.py (the canonical writer):
        # preserve model/sdk_uuid/used_tokens/context_updated_at so the Hub
        # reader resolves them for SDK sub-agents too (P5).
        new = {
            "agent": agent,
            "session_id": session_id,
            "pid": int(pid) if pid is not None else int(prev.get("pid") or _os.getpid()),
            "started_at": prev.get("started_at"),
            "last_prompt_at": prev.get("last_prompt_at"),
            "last_tool_at": prev.get("last_tool_at"),
            "last_stop_at": prev.get("last_stop_at"),
            "ended_at": prev.get("ended_at"),
            "model": prev.get("model"),
            "sdk_uuid": prev.get("sdk_uuid"),
            "used_tokens": prev.get("used_tokens"),
            "context_updated_at": prev.get("context_updated_at"),
        }
        if event == "start":
            new["started_at"] = now
            new["ended_at"] = None
            new["last_stop_at"] = None
        elif event == "prompt":
            new["last_prompt_at"] = now
            new["last_stop_at"] = None
            new["started_at"] = new["started_at"] or now
        elif event == "tool":
            new["last_tool_at"] = now
            new["started_at"] = new["started_at"] or now
        elif event == "stop":
            new["last_stop_at"] = now
        elif event == "end":
            new["ended_at"] = now
        # Keep the .json stem on the temp file (canonical writer uses
        # f"{path}.tmp.{pid}") so presence_gc reaps crash-orphaned temps (P31).
        tmp = path.parent / f"{path.name}.tmp.{_os.getpid()}"
        tmp.write_text(_json.dumps(new, separators=(",", ":")), encoding="utf-8")
        _os.replace(tmp, path)
    except OSError as exc:
        logger.debug("SDK presence write failed for %s: %s", session_id, exc)


def _dispatch_trace_content_enabled() -> bool:
    return os.environ.get("COS_DISPATCH_EVENT_CONTENT", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _emit_dispatch_trace(
    session_id: str, kind: str, formula_id: str | None, data: dict[str, Any] | None = None
) -> None:
    # Tee a dispatch lifecycle/turn event to the append-only cognition trace
    # sink (thinking_os.tracing) so the Hub can tail + replay the run. Fail-open:
    # a tracing failure must never alter the returned EvidenceBundle or break the
    # dispatch. Partial-message text rides along only when content is explicitly
    # enabled (COS_DISPATCH_EVENT_CONTENT), off by default.
    try:
        from thinking_os.tracing import emit

        emit(session_id, kind, data or {}, role=formula_id)
    except Exception as exc:
        logger.debug("dispatch trace emit skipped (%s): %s", kind, exc)


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

        # Resolve a routed tier alias (sonnet/opus/...) to a concrete adapter
        # model id BEFORE it reaches the SDK or the effort gate (R10/F6).
        resolved_model = _resolve_model_alias(request.model)

        # High-tier models get "xhigh"; everything else uses the SDK
        # default (None → "high"). See _XHIGH_EFFORT_MODEL_PREFIXES.
        effort: str | None = request.effort
        if resolved_model and resolved_model.startswith(_XHIGH_EFFORT_MODEL_PREFIXES):
            effort = effort or "xhigh"

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
        # Hub Settings → Claude Auth (TASK-756) first, so an OTEL var can never
        # shadow the ANTHROPIC_API_KEY override (disjoint key sets, but explicit
        # ordering keeps the precedence obvious to a future reader).
        env: dict[str, str] = _claude_auth_env(request.cwd or os.getcwd())
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
        max_turns = (
            request.max_turns
            if request.max_turns is not None
            else (3 if output_format is not None else 1)
        )
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
                **_failure_fields("error", f"max_budget_usd={request.max_budget_usd} exhausted"),
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
                **_failure_fields("error", "max_turns exhausted"),
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

        ok = bool(output_json) and any(k != "_meta" for k in output_json)
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
            **_failure_fields("ok" if ok else "error", error_str),
        )


# ---------------------------------------------------------------------------
# Factory — imported by core/thinking_os/dispatcher.py via importlib
# ---------------------------------------------------------------------------


def build_dispatcher() -> ClaudeSDKDispatcher:
    """Entry point the factory looks for when loading this module."""
    return ClaudeSDKDispatcher()
