"""core.web.routes.search — /api/search/* HTTP wrappers for search tools."""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Query

from .._deps import make_metrics_dep, make_rate_limit_dep
from .._envelope import ENVELOPE_ERROR_RESPONSES, unwrap

_CORE_DIR = Path(__file__).resolve().parents[3]
_TOS_DIR = _CORE_DIR / "thinking_os"
for _p in (_CORE_DIR, _TOS_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

router = APIRouter(prefix="/api/search", tags=["search"], responses=ENVELOPE_ERROR_RESPONSES)


def _db_conn() -> sqlite3.Connection:
    """Open the project SQLite DB for thinking_os search."""
    from web._project_context import current_db_path

    conn = sqlite3.connect(str(current_db_path()), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _unavailable(msg: str = "search tools unavailable") -> str:
    return json.dumps(
        {
            "ok": False,
            "error": {"category": "unavailable", "retryable": False, "message": msg},
        }
    )


def _module_disabled(module_id: str) -> bool:
    """True when module_id is disabled for the CURRENT request's project.

    The MCP cos_* capability gate (_shared._gated_module) reads $COS_STATE_DIR —
    the wrong project under the multi-project Hub — so these HTTP wrappers
    bypassed it and still served a disabled subsystem (audit F1 / B-3). Scope to
    the request's project via cli.subsystems.module_state instead. Fail-open: a
    gating error must never take the search route down."""
    try:
        from cli.subsystems import module_state  # type: ignore

        from web._project_context import current_project_root

        return not module_state(current_project_root()).get(module_id, True)
    except Exception:
        return False


def _gated(module_id: str) -> str:
    return json.dumps(
        {
            "ok": False,
            "error": {
                "category": "module_disabled",
                "retryable": False,
                "message": (
                    f"this search belongs to the disabled '{module_id}' module — "
                    f"enable it with `cos module enable {module_id}`"
                ),
            },
        }
    )


@router.get("/memory")
def memory_search(
    query: str = Query(..., description="Natural-language search query"),
    limit: int = Query(5),
    memory_type: str | None = Query(None),
    _rl=Depends(make_rate_limit_dep("search.memory")),
    _m=Depends(make_metrics_dep("search.memory")),
):
    """Search thinking_os memory (observations + learned patterns)."""
    if _module_disabled("memory"):
        return unwrap(_gated("memory"))
    try:
        from database import has_fts5_table  # type: ignore
        from tools.memory import memory_search as _search  # type: ignore
        from tools.retrieve import log_retrieval  # type: ignore
    except ImportError:
        # Try alternate import path (running from repo root rather than thinking_os dir).
        try:
            if str(_TOS_DIR) not in sys.path:
                sys.path.insert(0, str(_TOS_DIR))
            from database import has_fts5_table  # type: ignore
            from tools.memory import memory_search as _search  # type: ignore
            from tools.retrieve import log_retrieval  # type: ignore
        except ImportError as exc:
            return unwrap(_unavailable(f"memory search tools unavailable: {exc}"))

    conn = _db_conn()
    try:
        result = _search(
            conn,
            query=query,
            limit=limit,
            memory_type=memory_type or None,
            use_fts5=has_fts5_table(conn),
            include_body=True,
        )
        rids = log_retrieval(
            conn,
            layer="memory",
            query=query,
            rows=(result.get("results") or []) if isinstance(result, dict) else [],
        )
        if isinstance(result, dict):
            result["retrieval_ids"] = rids
    finally:
        conn.close()

    import json as _json

    return unwrap(
        _json.dumps(
            {
                "ok": True,
                "data": {
                    **(result if isinstance(result, dict) else {"results": result}),
                    "meta": {"layer": "memory", "query": query},
                },
            }
        )
    )


@router.get("/docs")
def doc_search(
    query: str = Query(..., description="Natural-language search query"),
    source_types: str | None = Query(None, description="Comma-separated source types"),
    limit: int = Query(5),
    mode: str = Query("auto"),
    _rl=Depends(make_rate_limit_dep("search.docs")),
    _m=Depends(make_metrics_dep("search.docs")),
):
    """Semantic search over project documentation chunks."""
    if _module_disabled("docs"):
        return unwrap(_gated("docs"))
    try:
        if str(_TOS_DIR) not in sys.path:
            sys.path.insert(0, str(_TOS_DIR))
        from tools.docs import doc_search as _doc_search  # type: ignore
        from tools.retrieve import log_retrieval  # type: ignore
    except ImportError as exc:
        return unwrap(_unavailable(f"doc search tools unavailable: {exc}"))

    types = [t.strip() for t in source_types.split(",") if t.strip()] if source_types else None
    mode_clean = mode if mode in ("auto", "semantic", "lexical") else "auto"

    conn = _db_conn()
    try:
        results = _doc_search(conn, query=query, source_types=types, limit=limit, mode=mode_clean)
        rids = log_retrieval(conn, layer="docs", query=query, rows=results)
    finally:
        conn.close()

    import json as _json

    return unwrap(
        _json.dumps(
            {
                "ok": True,
                "data": {
                    "results": results,
                    "count": len(results),
                    "retrieval_ids": rids,
                    "meta": {"layer": "docs", "query": query, "mode": mode_clean},
                },
            }
        )
    )


@router.get("/tasks")
def task_search(
    query: str = Query(..., description="Natural-language search query"),
    status: str | None = Query(None, description="open/wip/done/blocked"),
    domain: str | None = Query(None, description="BACKEND/FRONTEND/DOCS/INFRA/..."),
    limit: int = Query(10),
    _rl=Depends(make_rate_limit_dep("search.tasks")),
    _m=Depends(make_metrics_dep("search.tasks")),
):
    """Semantic + structured search over the Scrumban task store."""
    if _module_disabled("tasks"):
        return unwrap(_gated("tasks"))
    try:
        if str(_TOS_DIR) not in sys.path:
            sys.path.insert(0, str(_TOS_DIR))
        from tools.retrieve import log_retrieval  # type: ignore
        from tools.tasks import task_search as _task_search  # type: ignore
    except ImportError as exc:
        return unwrap(_unavailable(f"task search tools unavailable: {exc}"))

    conn = _db_conn()
    try:
        results = _task_search(
            conn,
            query=query,
            status=status or None,
            domain=domain or None,
            limit=limit,
        )
        rids = log_retrieval(conn, layer="tasks", query=query, rows=results)
    finally:
        conn.close()

    import json as _json

    return unwrap(
        _json.dumps(
            {
                "ok": True,
                "data": {
                    "results": results,
                    "count": len(results),
                    "retrieval_ids": rids,
                    "meta": {
                        "layer": "tasks",
                        "query": query,
                        "filters_applied": {"status": status or None, "domain": domain or None},
                    },
                },
            }
        )
    )
