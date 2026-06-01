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

from fastapi import APIRouter, Depends, Query

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
async def list_patterns(
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
        rows = conn.execute(
            f"SELECT {_COLUMNS} FROM learned_patterns{where} "
            "ORDER BY confidence DESC, impact_score DESC LIMIT ?",
            params + [limit],
        ).fetchall()
        total = conn.execute("SELECT COUNT(*) FROM learned_patterns").fetchone()[0]
    finally:
        conn.close()

    patterns = [dict(r) for r in rows]
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
