"""graph-os test fixtures.

Puts core/thinking_os on sys.path so tests can import the db module
directly (the MCP server does the same thing at runtime). Keeps tests
hermetic — every test gets a fresh SQLite file under a temp dir.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_GRAPH_OS_DIR = Path(__file__).resolve().parent.parent
_THINKING_OS_DIR = _GRAPH_OS_DIR.parent / "thinking_os"

if str(_THINKING_OS_DIR) not in sys.path:
    sys.path.insert(0, str(_THINKING_OS_DIR))
if str(_GRAPH_OS_DIR.parent) not in sys.path:
    sys.path.insert(0, str(_GRAPH_OS_DIR.parent))


@pytest.fixture()
def fresh_db_path(tmp_path: Path) -> str:
    """Return a fresh sqlite3 path inside tmp_path (no schema yet)."""
    return str(tmp_path / "graph-os-test.db")


@pytest.fixture()
def migrated_conn(fresh_db_path: str):
    """Return a freshly initialised sqlite3 connection at schema v12."""
    import db  # type: ignore

    conn = db.init_db(fresh_db_path)
    try:
        yield conn
    finally:
        conn.close()
