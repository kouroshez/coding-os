"""Coding OS — Agent Dispatcher Protocol."""

from __future__ import annotations

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
    formula_id: str  # e.g. "implementer"
    agent_file: str  # absolute path to F<N>_name.md
    prompt: str  # composed system+user prompt
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
    effort: str | None = None
    # Per-call cost ceiling (USD). None = no ceiling. Adapters that
    # cannot enforce this MUST surface a warning rather than silently
    # dropping the cap. The Claude adapter forwards this to
    # ClaudeAgentOptions.max_budget_usd; on exhaustion the SDK emits
    # subtype="error_max_budget_usd" which the dispatcher maps to
    # status="error" with the budget figure in `error`.
    max_budget_usd: float | None = None
    # Long-context opt-in. Adapters that support a
    # 1M-token context beta should expand the budget when True.
    long_context: bool = False
    # Target-runtime HINT (e.g. "codex"). One adapter per session stays the
    # invariant: a mismatch logs a warning in get_dispatcher and dispatch
    # proceeds on the session adapter (dispatcher-contract.md rule 6).
    adapter: str | None = None
    # Hop-cap on agentic turns for a single dispatch — defangs runaway recursive
    # delegation. None = the adapter default (Claude: 3 with an output schema,
    # else 1); an explicit value wins over that default.
    max_turns: int | None = None

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
    dispatcher_name: str = ""  # "claude-sdk" | "default" | ...
    raw_transcript: str | None = None  # optional, for debugging
    error_category: (
        Literal["capacity", "auth", "unavailable", "timeout", "provider", "invalid"] | None
    ) = None
    retryable: bool = False
    retry_after_s: int | None = None
    outcome: Literal["known_failed", "unknown"] = "unknown"


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


def _known_agents() -> set[str]:
    from thinking_os.adapter_registry import load_adapter_records

    return set(load_adapter_records())


def _detect_agent() -> str:
    known = _known_agents()
    explicit = os.environ.get("COS_AGENT", "").strip().lower()
    if explicit:
        return explicit

    agent_dir = os.environ.get("COS_AGENT_DIR", "")
    if agent_dir:
        name = Path(agent_dir).name.lower()
        if name in known:
            return name

    return "default"


def _try_load_adapter_dispatcher(agent: str) -> AgentDispatcher | None:
    from thinking_os.adapter_registry import load_adapter_records, load_entrypoint_module

    record = load_adapter_records().get(agent)
    if record is None or "dispatch" not in record.capabilities:
        return None
    module = load_entrypoint_module(record, "dispatch")
    if module is None:
        return None

    factory = getattr(module, "build_dispatcher", None)
    if factory is None:
        return None
    try:
        return factory()
    except Exception as exc:
        logger.warning("%s-sdk dispatcher init failed: %s", agent, exc)
        return None


def _try_load_claude_sdk_dispatcher() -> AgentDispatcher | None:
    """Backward-compat alias for the claude-specific load path."""
    return _try_load_adapter_dispatcher("claude")


def get_dispatcher(
    agent: str | None = None,
    request: DispatchRequest | None = None,
) -> AgentDispatcher:
    if os.environ.get("COS_FORCE_DEFAULT_DISPATCHER") == "1":
        from thinking_os.dispatchers.default import DefaultDispatcher

        return DefaultDispatcher()

    agent = agent or _detect_agent()

    if request is not None and request.adapter and request.adapter != agent:
        logger.warning(
            "adapter hint %r differs from session adapter %r — proceeding on %r "
            "(one adapter per session; dispatcher-contract.md rule 6)",
            request.adapter,
            agent,
            agent,
        )

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


def _default_model(record) -> str | None:
    for model in record.models:
        if model.get("default") and model.get("id"):
            return str(model["id"])
    return None


async def dispatch_request(request: DispatchRequest, db_path: str | Path) -> DispatchResult:
    from thinking_os import supervision

    project_root = (
        Path(request.cwd).resolve() if request.cwd else supervision.current_project_root()
    )
    policy = supervision.load_policy(project_root)
    if policy.get("enabled") is not True:
        return await get_dispatcher(request=request).dispatch(request)

    records = {record.id: record for record in supervision.eligible_records(project_root)}
    target = request.adapter or _detect_agent()
    candidates = [target] if target in records else []
    if not candidates and len(records) == 1:
        candidates = list(records)
    if policy.get("fallback_policy") == "next_eligible":
        candidates.extend(adapter_id for adapter_id in records if adapter_id not in candidates)
    if not candidates:
        return DispatchResult(
            formula_id=request.formula_id,
            status="error",
            error=f"no eligible dispatch adapter for {target!r}",
            error_category="unavailable",
            dispatcher_name="supervisor",
            outcome="known_failed",
        )

    last_result: DispatchResult | None = None
    for adapter_id in candidates:
        record = records[adapter_id]
        decision = supervision.check_capacity(db_path, adapter_id)
        if not decision.allowed:
            last_result = DispatchResult(
                formula_id=request.formula_id,
                status="error",
                error=decision.reason or f"{adapter_id} is cooling down",
                error_category="capacity",
                retryable=True,
                retry_after_s=decision.retry_after_s,
                dispatcher_name="supervisor",
                outcome="known_failed",
            )
            continue

        selected = request.model_copy(update={"adapter": adapter_id})
        if selected.effort and "effort_selection" not in record.capabilities:
            last_result = DispatchResult(
                formula_id=request.formula_id,
                status="error",
                error=f"adapter {adapter_id!r} does not support effort selection",
                error_category="invalid",
                dispatcher_name="supervisor",
                outcome="known_failed",
            )
            continue
        model_ids = {str(model.get("id")) for model in record.models if model.get("id")}
        if selected.model and model_ids and selected.model not in model_ids:
            if adapter_id != target or policy.get("fallback_policy") == "same_adapter_default":
                selected = selected.model_copy(update={"model": _default_model(record)})
            else:
                last_result = DispatchResult(
                    formula_id=request.formula_id,
                    status="error",
                    error=f"model {selected.model!r} is not declared by adapter {adapter_id!r}",
                    error_category="invalid",
                    dispatcher_name="supervisor",
                    outcome="known_failed",
                )
                continue
        if selected.effort and record.efforts and selected.effort not in record.efforts:
            last_result = DispatchResult(
                formula_id=request.formula_id,
                status="error",
                error=f"effort {selected.effort!r} is not declared by adapter {adapter_id!r}",
                error_category="invalid",
                dispatcher_name="supervisor",
                outcome="known_failed",
            )
            continue

        runtime = get_dispatcher(agent=adapter_id)
        if runtime.name == "default":
            last_result = DispatchResult(
                formula_id=request.formula_id,
                status="error",
                error=f"adapter {adapter_id!r} dispatch runtime is unavailable",
                error_category="unavailable",
                dispatcher_name="supervisor",
                outcome="known_failed",
            )
            continue

        result = await runtime.dispatch(selected)
        supervision.record_result(
            db_path,
            adapter_id,
            success=result.status == "ok",
            error_category=result.error_category,
            retryable=result.retryable,
            retry_after_s=result.retry_after_s,
            reason=result.error or "",
            policy=policy,
        )
        meta = result.output_json.setdefault("_meta", {})
        if isinstance(meta, dict):
            meta.update(
                {
                    "adapter": adapter_id,
                    "model": selected.model,
                    "effort": selected.effort,
                    "health_state": decision.state,
                    "health_probe": decision.probe,
                    "error_category": result.error_category,
                    "retry_after_s": result.retry_after_s,
                }
            )
        if (
            result.status == "error"
            and result.error_category == "capacity"
            and result.retryable
            and result.outcome == "known_failed"
            and policy.get("fallback_policy") == "next_eligible"
        ):
            last_result = result
            continue
        return result

    return last_result or DispatchResult(
        formula_id=request.formula_id,
        status="error",
        error="no dispatch adapter accepted the request",
        error_category="unavailable",
        dispatcher_name="supervisor",
        outcome="known_failed",
    )
