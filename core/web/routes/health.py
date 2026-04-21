"""core.web.routes.health — /health backend liveness endpoint.

PURPOSE: Expose a /health endpoint that checks if the graph_os backend is
         reachable and returns node/edge counts as a liveness signal.
INPUT:   HTTP GET (no params).
OUTPUT:  200 JSON {status: "ok", backend_id, node_count, edge_count, ...}.
DEPENDENCIES: fastapi, core.graph_os.backend.get_backend.
NOTES:  Never returns 5xx for backend unavailability — health endpoints must
        stay up.  Returns status: "degraded" when graph backend is missing.
"""

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
    """Backend liveness check with node/edge counts.

    PURPOSE: Verify graph backend is reachable; return counts as signal.
    INPUT:   none.
    OUTPUT:  JSON {status, backend_id, node_count, edge_count, ...}.
    DEPENDENCIES: graph_os.backend.get_backend, graph_os.backend.BackendUnavailable.
    NOTES:   Returns status: "degraded" instead of 5xx when backend fails.
    """
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

    except Exception as exc:  # noqa: BLE001 — health never raises
        result["status"] = "degraded"
        result["backend_id"] = "unavailable"
        result["reason"] = str(exc)

    return result
