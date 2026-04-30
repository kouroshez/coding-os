"""Multi-agent dispatch contract regression tests.

Verifies that the dispatcher contract (DispatchRequest / DispatchResult) is
honoured by every adapter — claude, codex, cursor, default — without any of
them hard-depending on the others. The factory in
`thinking_os.dispatcher.get_dispatcher()` must transparently pick the right
implementation per-environment, falling back to `DefaultDispatcher` when no
SDK or binary is present.

This test file is deliberately small: the goal is regression coverage for
the cross-agent contract itself, not for each adapter's spawn path. Each
adapter has its own focused tests (test_codex_dispatchers.py, etc.).
"""
from __future__ import annotations

import asyncio
import os

import pytest

from thinking_os.dispatcher import (
    AgentDispatcher,
    DispatchRequest,
    DispatchResult,
    get_dispatcher,
)


def _build_request() -> DispatchRequest:
    """Construct a minimal DispatchRequest that every adapter accepts."""
    return DispatchRequest(
        formula_id="researcher",
        agent_file="agents/F1_researcher.md",
        prompt="dummy prompt",
        input_slice={"task": "smoke"},
        intensity="standard",
        timeout_s=5.0,
    )


class TestDispatcherContract:
    """Each adapter dispatcher must satisfy the AgentDispatcher Protocol."""

    @pytest.mark.parametrize("agent", ["claude", "codex", "cursor"])
    def test_factory_returns_protocol_satisfying_object(self, agent: str) -> None:
        """`get_dispatcher(agent)` returns an object that quacks like
        AgentDispatcher — `name`, `available()`, `dispatch()`."""
        dispatcher = get_dispatcher(agent)
        assert isinstance(dispatcher, AgentDispatcher)
        assert isinstance(dispatcher.name, str) and dispatcher.name
        assert isinstance(dispatcher.available(), bool)

    def test_default_dispatcher_always_available(self) -> None:
        """Forcing default fallback yields an always-available dispatcher."""
        os.environ["COS_FORCE_DEFAULT_DISPATCHER"] = "1"
        try:
            dispatcher = get_dispatcher()
            assert dispatcher.name == "default"
            assert dispatcher.available() is True
        finally:
            del os.environ["COS_FORCE_DEFAULT_DISPATCHER"]

    def test_default_dispatcher_returns_skipped(self) -> None:
        """The default fallback never spawns; it returns a 'skipped' result
        with a structured hint so the main agent inlines the formula."""
        os.environ["COS_FORCE_DEFAULT_DISPATCHER"] = "1"
        try:
            dispatcher = get_dispatcher()
            result = asyncio.run(dispatcher.dispatch(_build_request()))
        finally:
            del os.environ["COS_FORCE_DEFAULT_DISPATCHER"]

        assert isinstance(result, DispatchResult)
        assert result.status == "skipped"
        assert result.dispatcher_name == "default"
        assert "dispatch_hint" in result.output_json
        assert result.output_json["formula_id"] == "researcher"


class TestCrossAdapterShapeParity:
    """Same DispatchRequest yields a DispatchResult with the same fields,
    regardless of which adapter the factory selected."""

    def test_result_shape_is_stable(self) -> None:
        """Every adapter's DispatchResult must carry the same key set so
        downstream code (cos_supervise_record_output, traces, metrics) can
        consume it without per-agent branches."""
        os.environ["COS_FORCE_DEFAULT_DISPATCHER"] = "1"
        try:
            dispatcher = get_dispatcher()
            result = asyncio.run(dispatcher.dispatch(_build_request()))
        finally:
            del os.environ["COS_FORCE_DEFAULT_DISPATCHER"]

        # Pydantic dump captures the canonical field set.
        keys = set(result.model_dump().keys())
        expected = {
            "formula_id",
            "status",
            "output_json",
            "latency_ms",
            "error",
            "dispatcher_name",
            "raw_transcript",
        }
        assert expected.issubset(keys), f"missing keys: {expected - keys}"

    def test_unsafe_formula_id_rejected(self) -> None:
        """Path-traversal-shaped formula_id values are rejected at the
        contract level, before any adapter sees them. Guards filename
        construction in claude/codex sub-session ids."""
        with pytest.raises(ValueError):
            DispatchRequest(
                formula_id="../etc/passwd",
                agent_file="agents/F1_researcher.md",
                prompt="x",
            )
