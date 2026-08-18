"""Formula dispatch: resolve the model, run the roles, persist the outcome.

Separate from the cognitive gates in cognition.py because this changes with the
dispatcher contract — adapters, models, cost accounting — while the gates change
with the reasoning protocol. Neither should drag the other into review.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any

from tools._shared import fail, ok, safe_tool

from ._cognition_shared import _cog, _load_bundle
from ._dispatch_persistence import (
    _emit_dispatch_metrics_safe,
    _persist_dispatch_output,
)
from ._dispatch_request import (
    _build_dispatch_request,
    _empirical_model as _empirical_model,
    _preset_role_hint as _preset_role_hint,
    _resolve_dispatch_model as _resolve_dispatch_model,
)

logger = logging.getLogger("thinking_os.cognition")


def _run_async_blocking(
    make_coroutine: Callable[[], Coroutine[Any, Any, Any]],
    timeout_s: float,
) -> Any:
    # Ask the environment, never an error message. Under FastMCP a loop always
    # owns this thread, so asyncio.run raises — and the wording it raises with
    # is a CPython detail that a string guard gets wrong exactly once: in
    # production, on the only path that matters, invisibly to unit tests that
    # call the tool from a thread with no loop of its own.
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(make_coroutine())

    box: dict[str, Any] = {}

    def _runner() -> None:
        loop = asyncio.new_event_loop()
        try:
            box["result"] = loop.run_until_complete(make_coroutine())
        except BaseException as exc:
            box["error"] = exc
        finally:
            loop.close()

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()
    thread.join(timeout=timeout_s)
    if "error" in box:
        raise box["error"]
    if "result" not in box:
        raise TimeoutError(f"dispatcher thread did not return within {timeout_s:.0f}s")
    return box["result"]


def _resolved_route(req: Any, result: Any) -> dict[str, Any]:
    # What core decided, for the columns an adapter is not obliged to echo.
    # `dispatcher_name` is the last resort because it names the dispatcher
    # implementation ("claude-sdk"), not the adapter id the policy selected.
    return {
        "adapter": req.adapter or result.dispatcher_name or None,
        "model": req.model or None,
        "effort": req.effort or None,
        "error_category": result.error_category,
        "error": result.error,
        "retry_after_s": result.retry_after_s,
    }


def register_cos_dispatch_formula(mcp, db_path):
    @mcp.tool(
        name="cos_dispatch_formula",
        description=(
            "Return the rendered agent prompt and input slice for a formula-agent. "
            "The main agent uses this to construct the subagent dispatch. "
            "Does NOT spawn the subagent — returns prompt text only."
        ),
    )
    @safe_tool
    def cos_dispatch_formula(
        formula_id: str,
        session_id: str,
        task_marker: str,
        persona_id: str,
        intensity: str = "standard",
    ) -> str:
        cog = _cog()
        agents = cog.load_agent_registry()
        meta = agents.get(formula_id)
        if not meta:
            return fail("not_found", f"No agent file for formula {formula_id}")

        agent_file = f"src/core/thinking_os/agents/{meta['_file']}"
        agent_path = Path(__file__).resolve().parent.parent / "agents" / meta["_file"]
        prompt_text = agent_path.read_text() if agent_path.exists() else ""

        bundle = _load_bundle(session_id, task_marker, persona_id)
        input_slice = cog.build_input_slice(formula_id, bundle)
        input_slice["intensity_steps"] = cog._intensity_steps(formula_id, intensity)

        return ok(
            {
                "formula_id": formula_id,
                "agent_file": agent_file,
                "prompt_text": prompt_text,
                "input_slice": input_slice,
                "timeout_s": meta.get("timeout_s", 90),
                "model_pref": meta.get("model_pref", {}),
            },
            meta={"layer": "routing"},
        )

    return cos_dispatch_formula


def register_cos_dispatch_formula_run(mcp, db_path):
    @mcp.tool(
        name="cos_dispatch_formula_run",
        description=(
            "EXPLICIT, OPT-IN sub-agent spawn for one role. Costs ~5k tokens "
            "per call (system prompt + input slice + completion) and rebuilds "
            "context inside the sub-agent. PREFER lazy-loading: read "
            "src/core/thinking_os/agents/<role>.md inline and produce the output "
            "schema yourself — same accuracy, far fewer tokens, no context "
            "rebuild penalty. Use this tool only when (a) the role's work is "
            "long-running and would dominate the main loop, or (b) you "
            "explicitly want a separate session for parallelism. If no SDK is "
            "available, returns status='skipped' and the main agent should "
            "execute the role's procedure inline."
        ),
    )
    @safe_tool
    def cos_dispatch_formula_run(
        formula_id: str,
        session_id: str,
        task_marker: str,
        persona_id: str,
        intensity: str = "standard",
        timeout_s: float | None = None,
        model: str = "",
        complexity: str = "",
        adapter: str = "",
        effort: str = "",
    ) -> str:
        from thinking_os import budget as _budget, dispatcher as _disp

        gate = _budget.check(db_path)
        if not gate.allowed:
            return fail("budget", gate.reason)
        chain_gate = _budget.chain_check(db_path, task_marker)
        if not chain_gate.allowed:
            return fail("budget", chain_gate.reason)

        try:
            req = _build_dispatch_request(
                formula_id,
                session_id,
                task_marker,
                persona_id,
                intensity,
                timeout_s,
                model,
                complexity,
                db_path,
                adapter=adapter,
                effort=effort,
            )
        except Exception as exc:
            return fail("validation", f"failed to build request: {exc}")

        # Trace event — visible in cos cognition trace replay so the
        # flowchart shows the actual sub-agent execution span.
        try:
            import tracing

            tracing.emit(
                session_id,
                "dispatch_started",
                {
                    "formula_id": formula_id,
                    "dispatcher_name": req.adapter or "supervisor",
                    "intensity": intensity,
                    "model": req.model,
                    "long_context": req.long_context,
                },
                role=formula_id,
                phase="EXECUTE",
            )
        except Exception as exc:
            logger.debug("dispatch_started trace emit failed: %s", exc)

        try:
            result = _run_async_blocking(
                lambda: _disp.dispatch_request(req, db_path),
                req.timeout_s + 10,
            )
        except TimeoutError as exc:
            return fail("unavailable", str(exc))
        except Exception as exc:
            return fail("internal", f"dispatch failed: {type(exc).__name__}: {exc}")

        route = _resolved_route(req, result)
        filled = 0
        # Every terminal outcome, not just the happy ones: a run that exhausted
        # its turn budget or hit a provider error still spent wall-clock and
        # tokens, and recording only successes makes a chronically broken route
        # indistinguishable from an idle one — both report zero.
        if result.status in ("ok", "timeout", "error") and result.output_json:
            filled = _persist_dispatch_output(
                session_id=session_id,
                task_marker=task_marker,
                persona_id=persona_id,
                formula_id=formula_id,
                output_json=result.output_json,
                status=result.status,
                latency_ms=result.latency_ms,
                db_path=db_path,
                raw_transcript=result.raw_transcript,
                resolved_route=route,
            )

        # T2.5 + T8.4: emit dispatch cost and duration as coding-os metrics
        # so cos_metric_trend surfaces spend over time.
        _emit_dispatch_metrics_safe(
            db_path=db_path,
            formula_id=formula_id,
            status=result.status,
            latency_ms=result.latency_ms,
            output_json=result.output_json,
            resolved_route=route,
        )

        # Trace event — pairs with dispatch_started above so the cognition
        # replay shows the full sub-agent execution span (not just supervisor
        # routing decision).
        try:
            import tracing

            _meta = result.output_json.get("_meta") if isinstance(result.output_json, dict) else {}
            _meta = _meta if isinstance(_meta, dict) else {}
            tracing.emit(
                session_id,
                "dispatch_completed",
                {
                    "formula_id": formula_id,
                    "status": result.status,
                    "latency_ms": result.latency_ms,
                    "cost_usd": _meta.get("total_cost_usd"),
                    "sub_session_id": _meta.get("session_id"),
                    "model": _meta.get("model") or route.get("model"),
                    "bundle_fields_filled": filled,
                    "error": result.error,
                    "error_category": result.error_category,
                    "retry_after_s": result.retry_after_s,
                    "adapter": _meta.get("adapter") or route.get("adapter"),
                },
                role=formula_id,
                phase="EXECUTE",
            )
        except Exception as exc:
            logger.debug("dispatch_completed trace emit failed: %s", exc)

        return ok(
            {
                "status": result.status,
                "formula_id": result.formula_id,
                "dispatcher_name": result.dispatcher_name,
                "adapter": route.get("adapter"),
                "model": route.get("model"),
                "latency_ms": result.latency_ms,
                "output_json": result.output_json,
                "error": result.error,
                "error_category": result.error_category,
                "retryable": result.retryable,
                "retry_after_s": result.retry_after_s,
                "outcome": result.outcome,
                "bundle_fields_filled": filled,
            },
            meta={"layer": "dispatch"},
        )

    return cos_dispatch_formula_run


def register_cos_dispatch_parallel_run(mcp, db_path):
    @mcp.tool(
        name="cos_dispatch_parallel_run",
        description=(
            "Spawn multiple formula-agents concurrently via asyncio.gather. "
            "Use when the supervisor returns action='dispatch_parallel' "
            "(e.g. security_auditor layers). Each output is persisted to the bundle. "
            "Returns list of DispatchResults in input order."
        ),
    )
    @safe_tool
    def cos_dispatch_parallel_run(
        formula_ids: list[str],
        session_id: str,
        task_marker: str,
        persona_id: str,
        intensity: str = "standard",
        timeout_s: float | None = None,
        model: str = "",
        complexity: str = "",
        adapter: str = "",
        effort: str = "",
    ) -> str:
        from thinking_os import budget as _budget, dispatcher as _disp

        if not formula_ids:
            return fail("validation", "formula_ids must be non-empty")

        # One check authorizes all N concurrent spawns, so it must gate on the
        # projected total — spent-only lets the fan-out overrun the cap.
        estimate = _budget.estimate_dispatch_cost(db_path, len(formula_ids))
        gate = _budget.check(db_path, additional_estimate_usd=estimate)
        if not gate.allowed:
            return fail("budget", gate.reason)
        chain_gate = _budget.chain_check(db_path, task_marker, additional_estimate_usd=estimate)
        if not chain_gate.allowed:
            return fail("budget", chain_gate.reason)

        try:
            requests = [
                _build_dispatch_request(
                    fid,
                    session_id,
                    task_marker,
                    persona_id,
                    intensity,
                    timeout_s,
                    model,
                    complexity,
                    db_path,
                    adapter=adapter,
                    effort=effort,
                )
                for fid in formula_ids
            ]
        except Exception as exc:
            return fail("validation", f"failed to build requests: {exc}")

        from thinking_os import supervision as _supervision

        parallel_limit = int(_supervision.load_policy().get("max_parallel") or 3)

        async def _gather_all():
            semaphore = asyncio.Semaphore(max(1, parallel_limit))

            async def _limited(req):
                async with semaphore:
                    return await _disp.dispatch_request(req, db_path)

            return await asyncio.gather(
                *(_limited(req) for req in requests),
                return_exceptions=True,
            )

        import time as _time

        t0 = _time.monotonic()
        deadline = max(req.timeout_s for req in requests) + 10
        try:
            gathered = _run_async_blocking(_gather_all, deadline)
        except TimeoutError as exc:
            return fail("unavailable", str(exc))
        except Exception as exc:
            return fail("internal", f"parallel dispatch failed: {type(exc).__name__}: {exc}")
        wall_ms = int((_time.monotonic() - t0) * 1000)

        results = []
        ok_count = 0
        for req, outcome in zip(requests, gathered, strict=False):
            if isinstance(outcome, Exception):
                results.append(
                    {
                        "status": "error",
                        "formula_id": req.formula_id,
                        "error": f"{type(outcome).__name__}: {outcome}",
                        "dispatcher_name": "supervisor",
                        "adapter": req.adapter or None,
                        "model": req.model or None,
                        "latency_ms": 0,
                        "output_json": {},
                        "error_category": "provider",
                        "retryable": False,
                        "retry_after_s": None,
                        "outcome": "unknown",
                        "bundle_fields_filled": 0,
                    }
                )
                continue
            route = _resolved_route(req, outcome)
            filled = 0
            if outcome.status == "ok" and outcome.output_json:
                filled = _persist_dispatch_output(
                    session_id=session_id,
                    task_marker=task_marker,
                    persona_id=persona_id,
                    formula_id=outcome.formula_id,
                    output_json=outcome.output_json,
                    status=outcome.status,
                    latency_ms=outcome.latency_ms,
                    db_path=db_path,
                    raw_transcript=outcome.raw_transcript,
                    resolved_route=route,
                )
                ok_count += 1
            results.append(
                {
                    "status": outcome.status,
                    "formula_id": outcome.formula_id,
                    "dispatcher_name": outcome.dispatcher_name,
                    "adapter": route.get("adapter"),
                    "model": route.get("model"),
                    "latency_ms": outcome.latency_ms,
                    "output_json": outcome.output_json,
                    "error": outcome.error,
                    "error_category": outcome.error_category,
                    "retryable": outcome.retryable,
                    "retry_after_s": outcome.retry_after_s,
                    "outcome": outcome.outcome,
                    "bundle_fields_filled": filled,
                }
            )

        return ok(
            {
                "results": results,
                "parallel_wall_ms": wall_ms,
                "ok_count": ok_count,
                "total": len(results),
            },
            meta={"layer": "dispatch"},
        )

    return cos_dispatch_parallel_run
