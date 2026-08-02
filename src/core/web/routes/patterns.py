"""core.web.routes.patterns — /api/patterns HTTP view of learned_patterns.

The "what has the agent learned, and how is each weighted?" window for the
Hub (TASK-055). The learned_patterns table had no UI surface — only a COUNT in
the health diagnostic — so the user could not see patterns, confidence, trust
tier, or decay. This route exposes the rows directly (read-only).
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from fastapi import APIRouter, Body, Depends, Query

from .._deps import make_metrics_dep, make_rate_limit_dep
from .._envelope import ENVELOPE_ERROR_RESPONSES, unwrap

_CORE_DIR = Path(__file__).resolve().parents[3]

router = APIRouter(prefix="/api/patterns", tags=["patterns"], responses=ENVELOPE_ERROR_RESPONSES)

_COLUMNS = (
    "id, pattern, memory_type, domain, source, confidence, decay_rate, "
    "impact_score, times_validated, times_violated, access_count, "
    "trust_tier, provenance, promoted_to, last_validated, last_accessed_at, created_at"
)


def _db_conn() -> sqlite3.Connection:
    """Open the active project SQLite DB."""
    from web._project_context import current_db_path

    conn = sqlite3.connect(str(current_db_path()), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


@router.get("")
def list_patterns(
    limit: int = Query(100, ge=1, le=500),
    trust_tier: str | None = Query(None, description="Filter by trust tier"),
    _rl=Depends(make_rate_limit_dep("patterns.list")),
    _m=Depends(make_metrics_dep("patterns.list")),
):
    """List learned patterns with their confidence / trust / decay weights."""
    conn = _db_conn()
    try:
        conditions = []
        params: list = []
        if trust_tier:
            conditions.append("trust_tier = ?")
            params.append(trust_tier)
        where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
        table_columns = {row[1] for row in conn.execute("PRAGMA table_info(learned_patterns)")}
        if not table_columns:
            # A never-initialized consumer DB has no learned_patterns table;
            # PRAGMA returns no rows. Render an empty page rather than letting
            # the SELECT below raise `no such table` as a bare 500.
            return unwrap(
                json.dumps(
                    {
                        "ok": True,
                        "data": {
                            "patterns": [],
                            "count": 0,
                            "total_count": 0,
                            "meta": {"layer": "learning", "truncated": False},
                        },
                    }
                )
            )
        # evidence_json arrived in migration v47 — a consumer DB the migrator
        # has not touched yet must still render the page.
        columns = _COLUMNS + (", evidence_json" if "evidence_json" in table_columns else "")
        rows = conn.execute(
            f"SELECT {columns} FROM learned_patterns{where} "
            "ORDER BY confidence DESC, impact_score DESC LIMIT ?",
            params + [limit],
        ).fetchall()
        total = conn.execute("SELECT COUNT(*) FROM learned_patterns").fetchone()[0]
    finally:
        conn.close()

    # Producer owns the tier field (API-contract-discipline): the UI renders the
    # tier label, never re-derives it from a raw % (which is meaningless to users).
    from thinking_os.tools.learning import pattern_tier

    patterns = [dict(r) for r in rows]
    for p in patterns:
        p["tier"] = pattern_tier(p.get("confidence"), p.get("times_validated"))
        p.setdefault("evidence_json", None)
    return unwrap(
        json.dumps(
            {
                "ok": True,
                "data": {
                    "patterns": patterns,
                    "count": len(patterns),
                    "total_count": total,
                    "meta": {"layer": "learning", "truncated": len(patterns) < total},
                },
            }
        )
    )


def _roi_trend(sessions: list[dict]) -> tuple[str, float]:
    """Improving when the recent half's mean friction rate is meaningfully below
    the older half's. Returns (trend, delta_pct) — delta<0 means improving."""
    if len(sessions) < 2:
        return ("insufficient", 0.0)
    mid = len(sessions) // 2
    older = [s["rate"] for s in sessions[:mid]] or [0.0]
    recent = [s["rate"] for s in sessions[mid:]] or [0.0]
    older_mean = sum(older) / len(older)
    recent_mean = sum(recent) / len(recent)
    if older_mean == 0:
        return ("flat", 0.0)
    delta_pct = round((recent_mean - older_mean) / older_mean * 100, 1)
    if recent_mean < older_mean * 0.9:
        return ("improving", delta_pct)
    if recent_mean > older_mean * 1.1:
        return ("worsening", delta_pct)
    return ("flat", delta_pct)


@router.get("/roi")
def learning_roi(
    limit: int = Query(20, ge=2, le=100),
    _rl=Depends(make_rate_limit_dep("patterns.roi")),
    _m=Depends(make_metrics_dep("patterns.roi")),
):
    """Per-session friction rate over recent sessions — does friction trend down (learning works)?"""
    conn = _db_conn()
    try:
        rows = conn.execute(
            "SELECT session_id, "
            "SUM(CASE WHEN memory_type IN ('hook_block', 'error') THEN 1 ELSE 0 END) AS friction, "
            "COUNT(*) AS total, MIN(created_at) AS started "
            "FROM observations WHERE session_id IS NOT NULL "
            # >= 5 observations = a real work session; drops tiny error-only
            # subagent/tool sessions that would skew the rate to 1.0.
            "GROUP BY session_id HAVING total >= 5 "
            "ORDER BY started DESC LIMIT ?",
            (limit,),
        ).fetchall()
        # The direct outcome signal: did surfaced lessons actually help?
        # (auto-validated at task-done + Hub thumbs). Stronger evidence than
        # the stumble trend once enough votes exist.
        try:
            validation = conn.execute(
                "SELECT COUNT(*) AS total, "
                "SUM(CASE WHEN was_helpful THEN 1 ELSE 0 END) AS helpful "
                "FROM pattern_validations "
                "WHERE created_at >= datetime('now', '-30 days')"
            ).fetchone()
            validations_30d = validation["total"] or 0
            helpful_30d = validation["helpful"] or 0
        except sqlite3.OperationalError:
            validations_30d = helpful_30d = 0
    finally:
        conn.close()
    sessions = [
        {
            "session_id": r["session_id"],
            "friction": r["friction"] or 0,
            "total": r["total"],
            "rate": round((r["friction"] or 0) / r["total"], 3) if r["total"] else 0.0,
            "started": r["started"],
        }
        for r in reversed(rows)  # chronological for the sparkline
    ]
    trend, delta_pct = _roi_trend(sessions)
    helpful_rate_30d = round(helpful_30d / validations_30d, 3) if validations_30d else None
    return unwrap(
        json.dumps(
            {
                "ok": True,
                "data": {
                    "sessions": sessions,
                    "count": len(sessions),
                    "trend": trend,
                    "delta_pct": delta_pct,
                    "validations_30d": validations_30d,
                    "helpful_rate_30d": helpful_rate_30d,
                    "meta": {"layer": "learning"},
                },
            }
        )
    )


@router.post("/{pattern_id}/validate")
def validate_pattern(
    pattern_id: int,
    was_helpful: bool = Body(..., embed=True),
    _rl=Depends(make_rate_limit_dep("patterns.validate")),
    _m=Depends(make_metrics_dep("patterns.validate")),
):
    """Record a user's 👍/👎 on a learned pattern — closes the validation loop (cos_learn_validate)."""
    from thinking_os.tools.learning import learn_validate

    conn = _db_conn()
    try:
        result = learn_validate(conn, pattern_id=pattern_id, was_helpful=was_helpful)
    finally:
        conn.close()
    if "error" in result:
        # A locked/core pattern is immutable — learn_validate returns trust_tier
        # on that rejection. It's a 400 against this resource's state, not a
        # missing row; only the genuine "pattern not found" maps to 404.
        category = "validation" if result.get("trust_tier") else "not_found"
        return unwrap(
            json.dumps(
                {
                    "ok": False,
                    "error": {
                        "category": category,
                        "message": result["error"],
                        "retryable": False,
                    },
                }
            )
        )
    return unwrap(json.dumps({"ok": True, "data": {**result, "meta": {"layer": "learning"}}}))
