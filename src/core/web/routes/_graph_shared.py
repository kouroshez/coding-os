"""Private base of the /api/graph route surface — the router and its import guard.

Imports neither sibling, so `graph` (the thin cos_graph_* wrappers) and
`_graph_export` (the cached export endpoint) can both register on one router
without a cycle.
"""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import APIRouter

from .._envelope import ENVELOPE_ERROR_RESPONSES

# Ensure core/ is on sys.path.
_CORE_DIR = Path(__file__).resolve().parents[3]
if str(_CORE_DIR) not in sys.path:
    sys.path.insert(0, str(_CORE_DIR))

router = APIRouter(prefix="/api/graph", tags=["graph"], responses=ENVELOPE_ERROR_RESPONSES)


def _tools():
    """Lazy import guard for graph_os tools."""
    try:
        from graph_os.tools import graph as _g  # type: ignore

        return _g
    except ImportError:
        return None


def _unavailable():
    import json

    return json.dumps(
        {
            "ok": False,
            "error": {
                "category": "unavailable",
                "retryable": False,
                "message": "graph_os package not importable; install graph_os extra",
            },
        }
    )
