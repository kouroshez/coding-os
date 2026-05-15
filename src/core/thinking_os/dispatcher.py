"""Coding OS — Agent Dispatcher Protocol (Phase N.SDK)."""

from __future__ import annotations

import importlib.util
import logging
import os
from pathlib import Path
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger("coding_os.dispatcher")


# ---------------------------------------------------------------------------
# IO contracts
# ---------------------------------------------------------------------------

class DispatchRequest(BaseModel):
    formula_id: str                        # e.g. "implementer"
    agent_file: str                        # absolute path to F<N>_name.md
    prompt: str                            # composed system+user prompt
    input_slice: dict[str, Any] = Field(default_factory=dict)
    persona_id: str | None = None
    intensity: Literal["light", "standard", "full"] = "standard"
    allowed_tools: list[str] = Field(default_factory=list)
    timeout_s: float = 300.0
    session_id: str | None = None
    cwd: str | None = None
    # Optional model id forwarded to the adapter (e.g. "claude-opus-4-7",
    # "claude-sonnet-4-6"). None = let the adapter pick its default. Kept
    # generic so non-Claude adapters can use their own model strings.
    model: str | None = None
    # Per-call cost ceiling (USD). None = no ceiling. Adapters that
    # cannot enforce this MUST surface a warning rather than silently
    # dropping the cap. The Claude adapter forwards this to
    # ClaudeAgentOptions.max_budget_usd; on exhaustion the SDK emits
    # subtype="error_max_budget_usd" which the dispatcher maps to
    # status="error" with the budget figure in `error`.
    max_budget_usd: float | None = None
    # Long-context opt-in (Phase Q.deep D6). Adapters that support a
    # 1M-token context beta should expand the budget when True.
    long_context: bool = False

    @field_validator("formula_id")
    @classmethod
    def _formula_id_is_safe(cls, v: str) -> str:
        import re as _re
        if not v or not _re.fullmatch(r"[A-Za-z0-9_-]+", v):
            raise ValueError(
                "formula_id must match [A-Za-z0-9_-]+ (got "
                f"{v!r}); dispatchers embed it in filenames."
            )
        return v


class DispatchResult(BaseModel):
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


def _known_agents() -> set[str]:
    try:
        if not _ADAPTERS_DIR.is_dir():
            return {"claude", "codex", "cursor"}
        return {
            d.name for d in _ADAPTERS_DIR.iterdir()
            if d.is_dir() and (d / "adapter.yaml").exists()
        } or {"claude", "codex", "cursor"}
    except OSError:
        return {"claude", "codex", "cursor"}


def _detect_agent() -> str:
    known = _known_agents()
    explicit = os.environ.get("COS_AGENT", "").strip().lower()
    if explicit in known:
        return explicit

    agent_dir = os.environ.get("COS_AGENT_DIR", "")
    if agent_dir:
        name = Path(agent_dir).name.lower()
        if name in known:
            return name

    return "default"


def _try_load_adapter_dispatcher(agent: str) -> "AgentDispatcher | None":
    adapter_path = _ADAPTERS_DIR / agent / "sdk_dispatcher.py"
    if not adapter_path.exists():
        return None

    mod_name = f"cos_adapters_{agent}_sdk_dispatcher"
    spec = importlib.util.spec_from_file_location(mod_name, adapter_path)
    if spec is None or spec.loader is None:
        return None
    try:
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except ImportError as exc:
        logger.debug("%s-sdk dispatcher unavailable: %s", agent, exc)
        return None
    except Exception as exc:
        logger.warning("%s-sdk dispatcher load failed: %s", agent, exc)
        return None

    factory = getattr(module, "build_dispatcher", None)
    if factory is None:
        return None
    try:
        return factory()
    except Exception as exc:
        logger.warning("%s-sdk dispatcher init failed: %s", agent, exc)
        return None


def _try_load_claude_sdk_dispatcher() -> "AgentDispatcher | None":
    """Backward-compat alias for the claude-specific load path."""
    return _try_load_adapter_dispatcher("claude")


def get_dispatcher(agent: str | None = None) -> AgentDispatcher:
    if os.environ.get("COS_FORCE_DEFAULT_DISPATCHER") == "1":
        from thinking_os.dispatchers.default import DefaultDispatcher
        return DefaultDispatcher()

    agent = agent or _detect_agent()

    if agent in _known_agents():
        sdk = _try_load_adapter_dispatcher(agent)
        if sdk is not None and sdk.available():
            return sdk
        logger.info(
            "%s-sdk dispatcher unavailable; falling back to default",
            agent,
        )

    from thinking_os.dispatchers.default import DefaultDispatcher
    return DefaultDispatcher()
