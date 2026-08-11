"""Claude adapter — SDK option construction and per-request resolution.

Everything the dispatcher needs to turn a project + a routed model tier into a
concrete `ClaudeAgentOptions`: the tool allow/deny floors, the model-alias map,
the Hub auth-mode override, the OTEL forwarding list, and the structured-output
schema lookup. Kept apart from the dispatch loop because option policy changes
on its own cadence (a new deny pattern, a new model id) and the loop does not.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

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
