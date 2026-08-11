"""core.web.routes._board_shared — the board router plus its DB and board_os handles.

Leaf module: it imports no sibling part, so any import order registers the
router exactly once.
"""

from __future__ import annotations

import logging
import sqlite3
import sys
from pathlib import Path

from fastapi import APIRouter

from .._envelope import ENVELOPE_ERROR_RESPONSES

_CORE_DIR = Path(__file__).resolve().parents[3]
if str(_CORE_DIR) not in sys.path:
    sys.path.insert(0, str(_CORE_DIR))

logger = logging.getLogger("coding_os.web.board")
router = APIRouter(prefix="/api/board", tags=["board"], responses=ENVELOPE_ERROR_RESPONSES)


def _db_conn() -> sqlite3.Connection:
    """Open the project SQLite DB for one request."""
    from web._project_context import current_db_path

    return sqlite3.connect(str(current_db_path()), check_same_thread=False)


def _board_tools():
    """Lazy import for board_os mcp_tools."""
    try:
        from board_os import mcp_tools  # type: ignore

        return mcp_tools
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
                "message": "board_os package not importable",
            },
        }
    )
