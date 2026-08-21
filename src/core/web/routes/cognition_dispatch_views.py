"""Dispatcher cost, roster and task-analysis views on /api/cognition.

The read-only reporting half of the surface: what a dispatch cost, whether the
cost table is even populated, which sub-agents ran, what tools they called, and
the one-shot task analysis. All four read the dispatch DB; none of them touch
the trace files or the chat session store.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path

from fastapi import Depends, HTTPException, Query

from .._deps import make_metrics_dep, make_rate_limit_dep
from .._envelope import unwrap
from ._cognition_base import _cognition_module, _db_path, _unavailable, router

logger = logging.getLogger(__name__)


def _auth_mode() -> str:
    """Whether reported cost is real spend (`api_key`) or notional (`subscription`).

    Under a subscription the SDK still emits total_cost_usd — the API-equivalent
    price of the tokens, not a charge — so the same number means two different
    things and the reader cannot tell which from the number alone.
    """
    db = _db_path()
    if db is None:
        return "unknown"
    settings = Path(db).parent / "hub-settings.json"
    try:
        raw = json.loads(settings.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "unknown"
    auth = raw.get("claude_auth")
    mode = auth.get("mode") if isinstance(auth, dict) else None
    return str(mode) if mode else "unknown"


@router.get("/cost")
def dispatcher_cost_summary(
    formula_id: str | None = Query(None, description="Filter to one formula"),
    limit: int = Query(50, ge=1, le=500),
    _rl=Depends(make_rate_limit_dep("cognition.cost")),
    _m=Depends(make_metrics_dep("cognition.cost")),
):
    """Aggregate dispatch cost by formula and day, plus a per-adapter rollup."""
    db = _db_path()
    if db is None:
        return unwrap(
            json.dumps(
                {
                    "ok": True,
                    "data": {
                        "rows": [],
                        "by_adapter": [],
                        "auth_mode": _auth_mode(),
                        "total_usd": 0.0,
                        "count": 0,
                        "meta": {"layer": "cognition"},
                    },
                }
            )
        )

    try:
        params: list = []
        # Every dispatch, not only the priced ones. Codex reports token counts
        # and no USD figure, so filtering on cost_usd hid 13 real codex runs
        # from the very rollup that exists to answer "how much did each runtime
        # get used". A NULL cost means unknown, not zero and not excluded:
        # `count` covers every run, `total_cost_usd` sums only what is known.
        where = "WHERE 1=1"
        if formula_id:
            where += " AND formula_id = ?"
            params.append(formula_id)
        # COALESCE, not a filter: rows predating adapter attribution must report as
        # `unattributed` rather than being folded into a real adapter's total —
        # the whole point of the split is that it can be trusted.
        query_sql = (
            f"SELECT formula_id, date(ts) as day, "
            f"COALESCE(NULLIF(adapter,''), 'unattributed') as adapter, "
            f"COALESCE(NULLIF(model,''), '') as model, "
            f"SUM(cost_usd) as total_cost_usd, COUNT(*) as count, "
            f"AVG(latency_ms) as avg_latency_ms "
            f"FROM formula_dispatches {where} "
            f"GROUP BY formula_id, day, adapter, model "
            f"ORDER BY day DESC, total_cost_usd DESC "
            f"LIMIT ?"
        )
        adapter_sql = (
            f"SELECT COALESCE(NULLIF(adapter,''), 'unattributed') as adapter, "
            f"SUM(cost_usd) as total_cost_usd, COUNT(*) as count, "
            f"AVG(latency_ms) as avg_latency_ms "
            f"FROM formula_dispatches {where} "
            f"GROUP BY adapter ORDER BY total_cost_usd DESC"
        )
        with sqlite3.connect(db) as conn:
            conn.row_factory = sqlite3.Row
            rows = [dict(r) for r in conn.execute(query_sql, [*params, limit]).fetchall()]
            by_adapter = [dict(r) for r in conn.execute(adapter_sql, params).fetchall()]
            # Total comes from the adapter rollup, which is unlimited; summing the
            # LIMITed rows would silently under-report once history outgrows it.
            total_usd = sum(r["total_cost_usd"] or 0 for r in by_adapter)
    except Exception as exc:
        return unwrap(
            json.dumps(
                {
                    "ok": False,
                    "error": {"category": "internal", "retryable": False, "message": str(exc)},
                }
            )
        )

    return unwrap(
        json.dumps(
            {
                "ok": True,
                "data": {
                    "rows": rows,
                    "by_adapter": by_adapter,
                    "auth_mode": _auth_mode(),
                    "total_usd": round(total_usd, 6),
                    "count": len(rows),
                    "meta": {"layer": "cognition"},
                },
            }
        )
    )


@router.get("/cost/health")
def dispatcher_cost_health(
    _rl=Depends(make_rate_limit_dep("cognition.cost_health")),
    _m=Depends(make_metrics_dep("cognition.cost_health")),
):
    """Cost-health gauges over formula_dispatches: MAD anomaly, burn-rate, budget ladder."""
    empty = {
        "anomaly": {"ok": True, "n": 0, "outliers": []},
        "burn": {"days": 0},
        "budget": {"level": "ok", "cap_usd": None, "spent_usd": 0.0, "allowed": True},
        "overall_ok": True,
        "meta": {"layer": "cognition"},
    }
    db = _db_path()
    if db is None:
        return unwrap(json.dumps({"ok": True, "data": empty}))
    try:
        from thinking_os import budget

        anomaly = budget.cost_anomaly(db)
        burn = budget.cost_burn_rate(db)
        gate = budget.check(db)
        data = {
            "anomaly": anomaly,
            "burn": burn,
            "budget": {
                "level": gate.level,
                "cap_usd": gate.cap_usd,
                "spent_usd": round(gate.spent_usd, 6),
                "allowed": gate.allowed,
            },
            "overall_ok": bool(anomaly.get("ok", True) and gate.level != "hard_stop"),
            "meta": {"layer": "cognition"},
        }
        return unwrap(json.dumps({"ok": True, "data": data}))
    except Exception as exc:
        logger.debug("cost/health failed, failing open: %s", exc)
        return unwrap(json.dumps({"ok": True, "data": empty}))


@router.get("/dispatchers")
def list_dispatchers(
    limit: int = Query(100, ge=1, le=1000),
    status: str | None = Query(None),
    _rl=Depends(make_rate_limit_dep("cognition.dispatchers")),
    _m=Depends(make_metrics_dep("cognition.dispatchers")),
):
    """List recent formula dispatches with telemetry (T19.1)."""
    db = _db_path()
    if db is None:
        return unwrap(
            json.dumps(
                {
                    "ok": True,
                    "data": {"dispatches": [], "count": 0, "meta": {"layer": "cognition"}},
                }
            )
        )

    try:
        params: list = []
        where = "WHERE cost_usd IS NOT NULL"
        if status:
            where += " AND status = ?"
            params.append(status)
        params.append(limit)
        with sqlite3.connect(db) as conn:
            conn.row_factory = sqlite3.Row
            rows = [
                dict(r)
                for r in conn.execute(
                    f"SELECT session_id, formula_id, ts, cost_usd, budget_usd, "
                    f"status, latency_ms "
                    f"FROM formula_dispatches {where} "
                    f"ORDER BY ts DESC LIMIT ?",
                    params,
                ).fetchall()
            ]
    except Exception as exc:
        return unwrap(
            json.dumps(
                {
                    "ok": False,
                    "error": {"category": "internal", "retryable": False, "message": str(exc)},
                }
            )
        )

    return unwrap(
        json.dumps(
            {
                "ok": True,
                "data": {"dispatches": rows, "count": len(rows), "meta": {"layer": "cognition"}},
            }
        )
    )


@router.get("/dispatchers/{session_id}/tools")
def dispatcher_tools(
    session_id: str,
    _rl=Depends(make_rate_limit_dep("cognition.dispatcher_tools")),
    _m=Depends(make_metrics_dep("cognition.dispatcher_tools")),
):
    """Parse tool_calls_jsonb for one dispatch session (T19.2)."""
    db = _db_path()
    if db is None:
        raise HTTPException(status_code=503, detail="DB not available")

    try:
        with sqlite3.connect(db) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT tool_calls_jsonb, tool_failures_jsonb "
                "FROM formula_dispatches WHERE session_id = ? "
                "ORDER BY ts DESC LIMIT 1",
                (session_id,),
            ).fetchone()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if row is None:
        raise HTTPException(status_code=404, detail=f"session {session_id!r} not found")

    def _parse(col: str | None) -> list:
        if not col:
            return []
        try:
            parsed = json.loads(col)
            return parsed if isinstance(parsed, list) else []
        except (json.JSONDecodeError, TypeError):
            return []

    tool_calls = _parse(row["tool_calls_jsonb"])
    failures = _parse(row["tool_failures_jsonb"])
    return unwrap(
        json.dumps(
            {
                "ok": True,
                "data": {
                    "session_id": session_id,
                    "tool_calls": tool_calls,
                    "failures": failures,
                    "count": len(tool_calls),
                    "meta": {"layer": "cognition"},
                },
            }
        )
    )


@router.get("/analyze")
def cognition_analyze(
    task_description: str = Query(...),
    complexity_hint: str | None = Query(None),
    _rl=Depends(make_rate_limit_dep("cognition.analyze")),
    _m=Depends(make_metrics_dep("cognition.analyze")),
):
    """Analyze a task via cos_analyze_task."""
    cog = _cognition_module()
    if cog is None:
        return unwrap(_unavailable())
    # The cognition module exposes analyze_task directly (not through MCP wrapper).
    try:
        if hasattr(cog, "analyze_task"):
            result = cog.analyze_task(task_description, complexity_hint=complexity_hint)
            return unwrap(result if isinstance(result, str) else json.dumps(result))
    except Exception as exc:
        return unwrap(
            json.dumps(
                {
                    "ok": False,
                    "error": {"category": "internal", "retryable": False, "message": str(exc)},
                }
            )
        )
    return unwrap(_unavailable("analyze_task not available in this cognition module version"))
