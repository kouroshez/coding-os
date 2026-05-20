"""core.web.routes.health — /health backend liveness endpoint."""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import APIRouter

_CORE_DIR = Path(__file__).resolve().parents[3]
if str(_CORE_DIR) not in sys.path:
    sys.path.insert(0, str(_CORE_DIR))

router = APIRouter(tags=["health"])


@router.get("/health")
async def health():
    """Backend liveness check with node/edge counts."""
    result: dict = {"status": "ok"}
    try:
        from graph_os.backend import BackendUnavailable, get_backend  # type: ignore

        backend = get_backend()
        result["backend_id"] = backend.backend_id

        # Count nodes/edges as a live probe.
        edges = backend.list_edges(limit=1)
        result["edge_sample"] = len(edges)

        # Try to get a rough node count via list_edges sampling.
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

    # V1: surface file_index_state row count + last-indexed timestamp
    # so agents (and humans on /api/health) can tell whether incremental
    # indexing has warm data. Never fails the health check — a missing
    # table / DB just omits the two fields' values below.
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
