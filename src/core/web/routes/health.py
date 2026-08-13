"""core.web.routes.health — backend liveness + DB row-count endpoints.

Both /health (legacy hub-wide) and /api/health (project-scoped via the
ProjectScopeMiddleware rewrite) point at the same handler.  When the
request arrived via /api/p/<slug>/health the middleware has bound the
slug's project scope, so the graph backend (get_backend → resolve_db_path)
and the file_index_state read (current_db_path) both resolve the
per-project coding-os.db rather than the launch-cwd default.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from fastapi import APIRouter

from .._envelope import safe_error_message

_CORE_DIR = Path(__file__).resolve().parents[3]
if str(_CORE_DIR) not in sys.path:
    sys.path.insert(0, str(_CORE_DIR))

logger = logging.getLogger("coding_os.web.health")

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
        result["reason"] = safe_error_message(exc, "graph backend unavailable", logger)

    result["file_index_state_rows"] = None
    result["file_index_state_last_indexed_at"] = None
    try:
        from thinking_os import database  # type: ignore
        from web._project_context import current_db_path  # type: ignore

        conn = database.init_db(current_db_path())
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
        result["file_index_state_error"] = safe_error_message(
            exc, "file_index_state unreadable", logger
        )

    return result


@router.get("/health")
def health():
    """Legacy hub-wide health endpoint (kept for back-compat)."""
    return _health_payload()


@router.get("/api/health")
def api_health():
    """Project-scoped health endpoint — rewritten by ProjectScopeMiddleware."""
    return _health_payload()


# Tables the Doctor sqlite tab surfaces. Names are the CANONICAL
# migration names (see src/core/thinking_os/database.py + the v* SQL
# files). Earlier this list referenced legacy names (`metrics`,
# `patterns`, `audit_log`) that never existed in any migration — they
# rendered as "absent" forever, masking the actual table state. Fixed
# 2026-05-23.
_DB_TABLES_OF_INTEREST = (
    "tasks",
    "observations",
    "agent_metrics",
    "task_outcomes",
    "learned_patterns",
    "session_summaries",
    "persona_selections",
    "formula_dispatches",
    "file_index_state",
)


@router.get("/api/health/db")
def api_health_db():
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
        payload["error"] = safe_error_message(exc, "database unreachable", logger)
        return payload
    try:
        # Discover which of our candidate tables actually live in this DB.
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        existing = {r[0] for r in rows}
        for table in _DB_TABLES_OF_INTEREST:
            if table not in existing:
                payload["tables"][table] = None
                continue
            try:
                count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                payload["tables"][table] = int(count or 0)
            except sqlite3.Error as exc:
                payload["tables"][table] = {
                    "error": safe_error_message(exc, f"table {table} unreadable", logger)
                }

        # Surface the self-diagnosis the counts-only view used to hide: the
        # numbers don't explain WHY a loop is dead.
        diagnostics: list[str] = []

        def _n(name: str) -> int:
            v = payload["tables"].get(name)
            return v if isinstance(v, int) else 0

        if _n("task_outcomes") >= 3 and _n("learned_patterns") == 0:
            diagnostics.append(
                f"Pipeline gap: {_n('task_outcomes')} task_outcomes but 0 learned_patterns "
                "— learn_extract has no fuel (check capture + outcome quality)."
            )
        for tbl in ("observations", "session_summaries"):
            if tbl in existing and _n(tbl) == 0:
                diagnostics.append(f"'{tbl}' empty — recall/learning signal missing.")
        if "agent_metrics" in existing and _n("agent_metrics") > 10:
            distinct = None
            try:
                distinct = conn.execute(
                    "SELECT COUNT(*) FROM "
                    "(SELECT DISTINCT agent_type, model, outcome FROM agent_metrics)"
                ).fetchone()[0]
            except sqlite3.Error as exc:
                distinct = None
                diagnostics.append(f"degeneracy check skipped (agent_metrics): {exc}")
            if distinct is not None and distinct <= 1:
                diagnostics.append(
                    f"agent_metrics degenerate: {_n('agent_metrics')} rows but 1 distinct "
                    "(agent_type, model, outcome) — telemetry carries no variance."
                )
        payload["diagnostics"] = diagnostics
    finally:
        conn.close()

    return payload


@router.get("/api/health/file-size")
def api_health_file_size():
    """Files over the line backstop, worst first — the Hub Doctor tab's code-budget panel.

    Same scanner `cos doctor` and `make check-file-size` use, so the CLI, CI, and
    the panel can never disagree about what counts as oversized.
    """
    import importlib.util

    from web._project_context import current_project_root  # type: ignore

    # _CORE_DIR is src/ despite the name (parents[3] of routes/health.py).
    scanner_path = _CORE_DIR / "core" / "scripts" / "check_file_size.py"
    spec = importlib.util.spec_from_file_location("cos_check_file_size", scanner_path)
    if spec is None or spec.loader is None:
        return {"ok": True, "available": False, "violations": []}
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
        result = module.scan(repo_root=current_project_root())
    except Exception as exc:
        return {
            "ok": True,
            "available": False,
            "error": safe_error_message(exc, "check unavailable", logger),
            "violations": [],
        }
    result["available"] = True
    return result
