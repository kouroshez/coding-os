"""
Coding OS — Agent Dispatcher Protocol (Phase N.SDK).

PURPOSE:      Agent-agnostic contract for spawning formula-agents. The
              supervisor state machine (cognition.py) decides WHICH formula
              to dispatch and WHAT input slice to send; this Protocol
              decides HOW to actually run it. Each adapter provides its
              own implementation — Claude uses claude-agent-sdk, others
              fall back to the default DB-only dispatcher.
INPUT:        DispatchRequest (formula_id, prompt, input_slice, persona,
              intensity, timeout_s).
OUTPUT:       DispatchResult (status, output_json, latency_ms, error).
DEPENDENCIES: pydantic, pathlib, os; no Claude- or Codex-specific imports.
NOTES:        core/ MUST stay agent-agnostic (Rule 1). Claude-specific code
              lives in adapters/claude/sdk_dispatcher.py. Factory
              `get_dispatcher()` picks the right implementation at runtime
              based on COS_AGENT env + SDK availability.
"""

from __future__ import annotations

import importlib.util
import logging
import os
from pathlib import Path
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field

logger = logging.getLogger("coding_os.dispatcher")


# ---------------------------------------------------------------------------
# IO contracts
# ---------------------------------------------------------------------------

class DispatchRequest(BaseModel):
    """
    PURPOSE: Everything a dispatcher needs to run one formula-agent.
    NOTES:   `input_slice` is the upstream-only bundle view built by
             build_input_slice(); dispatchers forward it as structured
             context rather than re-deriving from the full bundle.
    """
    formula_id: str                        # e.g. "F5"
    agent_file: str                        # absolute path to F<N>_name.md
    prompt: str                            # composed system+user prompt
    input_slice: dict[str, Any] = Field(default_factory=dict)
    persona_id: str | None = None
    intensity: Literal["light", "standard", "full"] = "standard"
    allowed_tools: list[str] = Field(default_factory=list)
    timeout_s: float = 300.0
    session_id: str | None = None
    cwd: str | None = None


class DispatchResult(BaseModel):
    """
    PURPOSE: Normalised outcome regardless of which adapter ran the agent.
    NOTES:   `output_json` must validate against the formula's output_schema
             from cognition_schemas (checked by caller, not dispatcher).
    """
    formula_id: str
    status: Literal["ok", "timeout", "error", "skipped"]
    output_json: dict[str, Any] = Field(default_factory=dict)
    latency_ms: int = 0
    error: str | None = None
    dispatcher_name: str = ""              # "claude-sdk" | "default" | ...
    raw_transcript: str | None = None      # optional, for debugging


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class AgentDispatcher(Protocol):
    """
    PURPOSE: Agent-agnostic dispatch contract. Implementations live in
             adapters (adapters/claude/sdk_dispatcher.py) or in
             core/thinking_os/dispatchers/ (default fallback).
    """
    name: str

    async def dispatch(self, request: DispatchRequest) -> DispatchResult:
        """Run one formula-agent and return its structured output."""
        ...

    def available(self) -> bool:
        """Cheap probe: is this dispatcher usable in the current env?"""
        ...


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

_ADAPTERS_DIR = Path(__file__).resolve().parent.parent.parent / "adapters"


def _detect_agent() -> str:
    """
    PURPOSE: Identify which adapter owns this session. Order of precedence:
             1. COS_AGENT env var (set by install.sh)
             2. $COS_AGENT_DIR folder name (.coding-os/claude/ vs codex/)
             3. Fallback to 'default'
    """
    explicit = os.environ.get("COS_AGENT", "").strip().lower()
    if explicit in ("claude", "codex", "cursor"):
        return explicit

    agent_dir = os.environ.get("COS_AGENT_DIR", "")
    if agent_dir:
        name = Path(agent_dir).name.lower()
        if name in ("claude", "codex", "cursor"):
            return name

    return "default"


def _try_load_claude_sdk_dispatcher() -> AgentDispatcher | None:
    """
    PURPOSE: Dynamically import adapters/claude/sdk_dispatcher.py without
             making core/ depend on it. Returns None if the extra isn't
             installed OR the adapter file is absent.
    """
    adapter_path = _ADAPTERS_DIR / "claude" / "sdk_dispatcher.py"
    if not adapter_path.exists():
        return None

    spec = importlib.util.spec_from_file_location(
        "cos_adapters_claude_sdk_dispatcher", adapter_path,
    )
    if spec is None or spec.loader is None:
        return None
    try:
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except ImportError as exc:
        logger.debug("claude-sdk dispatcher unavailable: %s", exc)
        return None
    except Exception as exc:
        logger.warning("claude-sdk dispatcher load failed: %s", exc)
        return None

    factory = getattr(module, "build_dispatcher", None)
    if factory is None:
        return None
    try:
        return factory()
    except Exception as exc:
        logger.warning("claude-sdk dispatcher init failed: %s", exc)
        return None


def get_dispatcher(agent: str | None = None) -> AgentDispatcher:
    """
    PURPOSE:      Return the right dispatcher for the current adapter.
    INPUT:        Optional agent override; defaults to _detect_agent().
    OUTPUT:       A live AgentDispatcher (claude-sdk or default fallback).
    DEPENDENCIES: dispatchers/default.py is always available; claude-sdk is
                  best-effort (requires `uv sync --extra claude-sdk` and
                  adapters/claude/sdk_dispatcher.py).
    NOTES:        If COS_FORCE_DEFAULT_DISPATCHER=1, always returns default.
                  This lets tests exercise the fallback path on a Claude
                  machine, and lets the user disable real spawning.
    """
    if os.environ.get("COS_FORCE_DEFAULT_DISPATCHER") == "1":
        from dispatchers.default import DefaultDispatcher
        return DefaultDispatcher()

    agent = agent or _detect_agent()

    if agent == "claude":
        sdk = _try_load_claude_sdk_dispatcher()
        if sdk is not None and sdk.available():
            return sdk
        logger.info(
            "claude-sdk dispatcher unavailable; falling back to default "
            "(install with: uv sync --extra claude-sdk)"
        )

    from dispatchers.default import DefaultDispatcher
    return DefaultDispatcher()
