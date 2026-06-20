"""logging_os test fixtures.

Puts core/thinking_os (and core/) on sys.path so that when a logging_os
test calls thinking_os.database.init_db, the migrations' bare imports
(``from sanitizer import scrub_username`` in _migrate_v37) resolve the same
way they do under the MCP server and the thinking_os test suite. Without
this, the db-sink tests abort with ModuleNotFoundError: No module named
'sanitizer' (audit-2026-06 R15 / TASK-438). Mirrors
core/thinking_os/tests/conftest.py.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_CORE_DIR = Path(__file__).resolve().parent.parent.parent  # src/core
_THINKING_OS_DIR = _CORE_DIR / "thinking_os"

for _p in (_THINKING_OS_DIR, _CORE_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


_LOG_ENV_KEYS = (
    "COS_LOG_LEVEL",
    "COS_LOG_DB_MIN_LEVEL",
    "COS_LOG_FILE",
    "COS_LOG_JSON",
    "COS_LOG_FORCE_PRETTY",
    "COS_LOG_MAX_LINES",
)


@pytest.fixture(autouse=True)
def _isolate_log_env():
    """Snapshot/restore COS_LOG_* per test. setup()/install_bridge write
    COS_LOG_LEVEL into os.environ DIRECTLY (outside monkeypatch's tracking), so
    without this a floor set by one test leaks into the next and (since the sink
    floors became per-sink, TASK-473) gates its human sinks unexpectedly."""
    saved = {key: os.environ.get(key) for key in _LOG_ENV_KEYS}
    yield
    for key, value in saved.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
