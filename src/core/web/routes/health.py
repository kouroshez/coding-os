"""core.web.routes.health — backend liveness + DB row-count endpoints.

Both /health (legacy hub-wide) and /api/health (project-scoped via the
ProjectScopeMiddleware rewrite) point at the same handler.  When the
request arrived via /api/p/<slug>/health the middleware has already
swapped thinking_os's active project root, so resolve_db_path()
returns the per-project coding-os.db rather than the cwd default.
"""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import APIRouter

_CORE_DIR = Path(__file__).resolve().parents[3]
if str(_CORE_DIR) not in sys.path:
    sys.path.insert(0, str(_CORE_DIR))

router = APIRouter(tags=["health"])


def _health_payload() -> dict:
    result: dict = {"status": "ok"}
    try:
        from graph_os.backend import get_backend  # type: ignore

        backend = get_backend()
        result["backend_id"] = backend.backend_id

        edges = backend.list_edges(limit=1)
        result["edge_sample"] = len(edges)

        sample_edges = backend.list_edges(limit=100)
        uids: set[str] = set()
        for e in sample_edges:
            uids.add(e.source_uid)
            uids.add(e.target_uid)
        result["node_count_sample"] = len(uids)
        result["edge_count_sample"] = len(sample_edges)
    except Exception as exc:
        result["status"] = "degraded"
        result["backend_id"] = "unavailable"
        result["reason"] = str(exc)

    result["file_index_state_rows"] = None
    result["file_index_state_last_indexed_at"] = None
    try:
        from thinking_os import database  # type: ignore

        conn = database.init_db()
        try:
            if database.has_file_index_state_table(conn):
                row = conn.execute(
                    "SELECT COUNT(*), MAX(last_indexed_at) FROM file_index_state"
                ).fetchone()
                if row is not None:
                    result["file_index_state_rows"] = int(row[0] or 0)
                    result["file_index_state_last_indexed_at"] = (
                        int(row[1]) if row[1] is not None else None
                    )
        finally:
            conn.close()
    except Exception as exc:
        result["file_index_state_error"] = str(exc)

    return result


@router.get("/health")
async def health():
    """Legacy hub-wide health endpoint (kept for back-compat)."""
    return _health_payload()


@router.get("/api/health")
async def api_health():
    """Project-scoped health endpoint — rewritten by ProjectScopeMiddleware."""
    return _health_payload()


_DB_TABLES_OF_INTEREST = (
    "tasks",
    "observations",
    "metrics",
    "task_outcomes",
    "patterns",
    "session_summaries",
    "persona_selections",
    "formula_dispatches",
    "audit_log",
    "file_index_state",
)


@router.get("/api/health/db")
async def api_health_db():
    """Per-project sqlite row counts grouped by table.

    Returns the project's coding-os.db row counts for the tables the
    Doctor tab surfaces — empty result means the table is absent from
    this DB's migration history (treated as 0, not error).
    """
    from web._project_context import current_db_path  # type: ignore

    db_path = current_db_path()
    payload: dict = {
        "db_path": str(db_path),
        "exists": db_path.exists(),
        "size_bytes": (db_path.stat().st_size if db_path.exists() else 0),
        "tables": {},
    }
    if not db_path.exists():
        return payload

    import sqlite3

    try:
        conn = sqlite3.connect(str(db_path))
    except sqlite3.Error as exc:
        payload["error"] = str(exc)
        return payload
    try:
        # Discover which of our candidate tables actually live in this DB.
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        existing = {r[0] for r in rows}
        for table in _DB_TABLES_OF_INTEREST:
            if table not in existing:
                payload["tables"][table] = None
                continue
            try:
                count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                payload["tables"][table] = int(count or 0)
            except sqlite3.Error as exc:
                payload["tables"][table] = {"error": str(exc)}
    finally:
        conn.close()

    return payload
