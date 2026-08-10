"""Formula dispatch: resolve the model, run the roles, persist the outcome.

Separate from the cognitive gates in cognition.py because this changes with the
dispatcher contract — adapters, models, cost accounting — while the gates change
with the reasoning protocol. Neither should drag the other into review.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
from pathlib import Path
from typing import Any

from tools._shared import fail, ok, safe_tool

from ._cognition_shared import (
    _all_bundle_fields,
    _cog,
    _load_bundle,
    _now_iso,
    _resolve_role_persistence,
    _save_bundle,
)

logger = logging.getLogger("thinking_os.cognition")


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


def _persist_dispatch_output(
    *,
    session_id: str,
    task_marker: str,
    persona_id: str,
    formula_id: str,
    output_json: dict,
    status: str,
    latency_ms: int,
    db_path: str,
    raw_transcript: str | None = None,
) -> int:
    bundle = _load_bundle(session_id, task_marker, persona_id)
    # Data-driven role → bundle field + Pydantic class resolution.
    # Role frontmatter declares `output_schema: cognition.<X>Output`;
    # `bundle_field` defaults to role id but can be overridden in frontmatter.
    field, cls = _resolve_role_persistence(formula_id)
    validation_failed = False
    if field and cls and status == "ok":
        try:
            parsed = cls.model_validate(output_json)
            setattr(bundle, field, parsed)
        except Exception as exc:
            # T1.6 — Pydantic validation runs BEFORE persistence.
            # On failure: mark degraded, skip the formula_dispatches INSERT
            # entirely (row would carry untrusted output_hash). Bundle still
            # saved with degraded_formulas marker so the supervisor can
            # backtrack.
            logger.warning(
                "Failed to validate %s output against schema: %s",
                formula_id,
                exc,
            )
            bundle.degraded_formulas.append(formula_id)
            status = "fail"
            validation_failed = True
    elif status == "timeout":
        bundle.degraded_formulas.append(formula_id)

    _save_bundle(session_id, bundle)

    # T1.6: skip the dispatch row INSERT when schema validation failed.
    # Returning the bundle field count keeps the caller signature stable.
    if validation_failed:
        return sum(1 for f in _all_bundle_fields() if getattr(bundle, f, None) is not None)

    raw = json.dumps(output_json, sort_keys=True, default=str).encode()
    output_hash = hashlib.sha256(raw).hexdigest()[:16]
    input_hash = hashlib.sha256(f"{session_id}:{formula_id}".encode()).hexdigest()[:16]
    # pull telemetry the Claude dispatcher stamps
    # into output_json["_meta"] (cost_usd, usage, model_usage, tool_calls,
    # tool_failures) and persist into the v23 columns. JSON-encoded so
    # the schema migration stays append-only — readers parse on demand.
    meta = output_json.get("_meta") if isinstance(output_json, dict) else None
    meta = meta if isinstance(meta, dict) else {}
    cost_usd_raw = meta.get("total_cost_usd")
    if isinstance(cost_usd_raw, (int, float)):
        cost_usd_val: float | None = float(cost_usd_raw)
    else:
        cost_usd_val = None

    def _jsonb(value: Any) -> str | None:
        if value is None:
            return None
        try:
            return json.dumps(value, default=str, sort_keys=True)
        except (TypeError, ValueError):
            return None

    try:
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "INSERT INTO formula_dispatches "
                "(session_id, task_marker, persona_id, formula_id, input_hash, "
                "output_hash, latency_ms, status, ts, "
                "cost_usd, budget_usd, usage_jsonb, model_usage_jsonb, "
                "tool_calls_jsonb, tool_failures_jsonb, "
                "sub_session_id, model, checkpoints_jsonb, error, raw_transcript, "
                "adapter, effort, error_category, retry_after_s, health_state, health_probe) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    session_id,
                    task_marker,
                    persona_id,
                    formula_id,
                    input_hash,
                    output_hash,
                    latency_ms,
                    status,
                    _now_iso(),
                    cost_usd_val,
                    meta.get("budget_usd"),
                    _jsonb(meta.get("usage")),
                    _jsonb(meta.get("model_usage")),
                    _jsonb(meta.get("tool_calls")),
                    _jsonb(meta.get("tool_failures")),
                    meta.get("session_id"),
                    meta.get("model"),
                    _jsonb(meta.get("checkpoints")),
                    str(meta.get("error"))[:1000] if meta.get("error") else None,
                    raw_transcript[:50000] if raw_transcript else None,
                    meta.get("adapter"),
                    meta.get("effort"),
                    meta.get("error_category"),
                    meta.get("retry_after_s"),
                    meta.get("health_state"),
                    1 if meta.get("health_probe") else 0,
                ),
            )
    except Exception as exc:
        logger.debug("formula_dispatches insert failed: %s", exc)

    return sum(1 for f in _all_bundle_fields() if getattr(bundle, f, None) is not None)


def _emit_dispatch_metrics_safe(
    *,
    db_path: str,
    formula_id: str,
    status: str,
    latency_ms: int,
    output_json: dict,
) -> None:
    import sqlite3 as _sqlite3

    try:
        from tools.metrics import metric_record  # type: ignore[import]

        _outcome_map = {
            "ok": "success",
            "timeout": "blocked",
            "error": "partial",
            "skipped": "partial",
        }
        outcome = _outcome_map.get(status, "partial")
        meta = output_json.get("_meta") if isinstance(output_json, dict) else {}
        meta = meta if isinstance(meta, dict) else {}
        model_used = meta.get("model") or None
        with _sqlite3.connect(db_path) as conn:
            metric_record(
                conn,
                agent_type="dispatch",
                outcome=outcome,
                duration_ms=latency_ms,
                domain=formula_id,
                model=model_used,
                complexity="CLEAR",
            )
    except Exception as exc:
        logger.debug("dispatch metric emit failed: %s", exc)


def _preset_role_hint(session_id: str, formula_id: str, db_path) -> dict:
    # Tier-2 lookup (claude-sdk.md §7.3): the session's composed preset is
    # read back from persona_selections (preset_id lives in its task_marker
    # column — see register_cos_compose_chain's INSERT), then that preset's
    # roles_adapter_hints[formula_id]. Fail-open: hints are advisory.
    if not db_path:
        return {}
    try:
        import sqlite3 as _sqlite3

        conn = _sqlite3.connect(db_path)
        try:
            row = conn.execute(
                "SELECT task_marker FROM persona_selections WHERE session_id = ? "
                "ORDER BY rowid DESC LIMIT 1",
                (session_id,),
            ).fetchone()
        finally:
            conn.close()
        preset_id = row[0] if row and row[0] else ""
        if not preset_id:
            return {}
        import formula_composer

        presets, _version = formula_composer.load_presets()
        preset = next((p for p in presets if p.get("id") == preset_id), {})
        hint = (preset.get("roles_adapter_hints") or {}).get(formula_id) or {}
        return hint if isinstance(hint, dict) else {}
    except Exception as exc:
        logger.debug("preset hint lookup failed: %s", exc)
        return {}


def _empirical_model(complexity: str, db_path) -> str:
    # Tier-4: cos_route_model's recommendation, only when real outcome
    # history backs it (cold-start static defaults must not override the
    # SDK default for every dispatch).
    if not db_path or not complexity.strip():
        return ""
    try:
        import sqlite3 as _sqlite3

        from tools.routing import route_model_bandit

        conn = _sqlite3.connect(db_path)
        try:
            result = route_model_bandit(conn, complexity=complexity.strip().upper())
        finally:
            conn.close()
        if int(result.get("data_points") or 0) > 0:
            return str(result.get("recommended_model") or "")
        return ""
    except Exception as exc:
        logger.debug("empirical model lookup failed: %s", exc)
        return ""


def _resolve_dispatch_model(
    formula_id: str,
    session_id: str,
    meta: dict,
    model: str,
    complexity: str,
    db_path,
    supervised: dict[str, str] | None = None,
) -> str:
    level = complexity.strip().lower()
    hint_pref = _preset_role_hint(session_id, formula_id, db_path).get("model_pref") or {}
    role_pref = meta.get("model_pref") or {}
    resolved = ""
    for candidate, source in (
        (model.strip(), "explicit"),
        ((supervised or {}).get("model", ""), "supervision_policy"),
        (hint_pref.get(level, ""), "preset_hint"),
        (role_pref.get(level, ""), "role_pref"),
    ):
        if candidate:
            logger.info("dispatch model resolved for %s: %s via %s", formula_id, candidate, source)
            resolved = candidate
            break
    if not resolved:
        # Empirical is the expensive tier (sqlite connect + bandit query/sampling)
        # — consult it lazily, only when the static tiers all miss.
        empirical = _empirical_model(complexity, db_path)
        if empirical:
            logger.info("dispatch model resolved for %s: %s via empirical", formula_id, empirical)
            resolved = empirical
    # Cost-routed independent reviewer: a review role runs one tier cheaper than
    # the generator. Gated by COS_ROUTER_REVIEWER_CHEAPER (default off, unchanged).
    if resolved and os.environ.get("COS_ROUTER_REVIEWER_CHEAPER"):
        from tools.routing import _REVIEW_ROLES, reviewer_model

        if formula_id in _REVIEW_ROLES:
            cheaper = reviewer_model(resolved)
            if cheaper and cheaper != resolved:
                logger.info("reviewer %s downgraded to cheaper tier %s", formula_id, cheaper)
                resolved = cheaper
    return resolved


def _build_dispatch_request(
    formula_id: str,
    session_id: str,
    task_marker: str,
    persona_id: str,
    intensity: str,
    timeout_s: float | None,
    model: str = "",
    complexity: str = "",
    db_path=None,
    adapter: str = "",
    effort: str = "",
):
    """Build a DispatchRequest from session state (shared by run-one and run-parallel)."""
    from thinking_os import dispatcher as _disp  # lazy: avoid circular at import time

    cog = _cog()
    agents = cog.load_agent_registry()
    meta = agents.get(formula_id) or {}
    agent_file_rel = f"src/core/thinking_os/agents/{meta.get('_file', f'{formula_id}.md')}"
    agent_path = Path(__file__).resolve().parent.parent / "agents" / meta.get("_file", "")
    prompt_text = agent_path.read_text() if agent_path.exists() else ""

    bundle = _load_bundle(session_id, task_marker, persona_id)
    input_slice = cog.build_input_slice(formula_id, bundle)
    input_slice["intensity_steps"] = cog._intensity_steps(formula_id, intensity)

    from thinking_os import supervision

    supervised = supervision.role_policy(formula_id, complexity=complexity)
    resolved_model = _resolve_dispatch_model(
        formula_id, session_id, meta, model, complexity, db_path, supervised
    )

    return _disp.DispatchRequest(
        formula_id=formula_id,
        agent_file=str(agent_path if agent_path.exists() else agent_file_rel),
        prompt=prompt_text,
        input_slice=input_slice,
        persona_id=persona_id,
        intensity=intensity if intensity in ("light", "standard", "full") else "standard",
        timeout_s=float(timeout_s) if timeout_s else float(meta.get("timeout_s", 300)),
        session_id=session_id,
        long_context=bool(meta.get("long_context", False)),
        model=resolved_model or None,
        adapter=adapter.strip() or supervised.get("adapter") or None,
        effort=effort.strip() or supervised.get("effort") or None,
        complexity=complexity.strip(),
    )


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
        import asyncio as _asyncio

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
            result = _asyncio.run(_disp.dispatch_request(req, db_path))
        except RuntimeError as exc:
            # Nested loop — fall back to a fresh thread-owned loop
            if "already running" in str(exc):
                import threading

                box: dict = {}

                def _runner():
                    loop = _asyncio.new_event_loop()
                    try:
                        box["result"] = loop.run_until_complete(
                            _disp.dispatch_request(req, db_path)
                        )
                    finally:
                        loop.close()

                t = threading.Thread(target=_runner, daemon=True)
                t.start()
                t.join(timeout=req.timeout_s + 10)
                if "result" not in box:
                    return fail("transient", "dispatcher thread did not return")
                result = box["result"]
            else:
                return fail("internal", f"asyncio.run failed: {exc}")

        filled = 0
        if result.status in ("ok", "timeout") and result.output_json:
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
            )

        # T2.5 + T8.4: emit dispatch cost and duration as coding-os metrics
        # so cos_metric_trend surfaces spend over time.
        _emit_dispatch_metrics_safe(
            db_path=db_path,
            formula_id=formula_id,
            status=result.status,
            latency_ms=result.latency_ms,
            output_json=result.output_json,
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
                    "model": _meta.get("model"),
                    "bundle_fields_filled": filled,
                    "error": result.error,
                    "error_category": result.error_category,
                    "retry_after_s": result.retry_after_s,
                    "adapter": _meta.get("adapter"),
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
        import asyncio as _asyncio

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
            semaphore = _asyncio.Semaphore(max(1, parallel_limit))

            async def _limited(req):
                async with semaphore:
                    return await _disp.dispatch_request(req, db_path)

            return await _asyncio.gather(
                *(_limited(req) for req in requests),
                return_exceptions=True,
            )

        import time as _time

        t0 = _time.monotonic()
        try:
            gathered = _asyncio.run(_gather_all())
        except RuntimeError:
            # Nested-loop fallback: run in a dedicated thread with fresh loop
            import threading

            box: dict = {}

            def _runner():
                loop = _asyncio.new_event_loop()
                try:
                    box["result"] = loop.run_until_complete(_gather_all())
                finally:
                    loop.close()

            t = threading.Thread(target=_runner, daemon=True)
            t.start()
            deadline = max(req.timeout_s for req in requests) + 10
            t.join(timeout=deadline)
            gathered = box.get("result", [])
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
                )
                ok_count += 1
            results.append(
                {
                    "status": outcome.status,
                    "formula_id": outcome.formula_id,
                    "dispatcher_name": outcome.dispatcher_name,
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
