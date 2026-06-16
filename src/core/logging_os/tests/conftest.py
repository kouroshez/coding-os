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

import sys
from pathlib import Path

_CORE_DIR = Path(__file__).resolve().parent.parent.parent  # src/core
_THINKING_OS_DIR = _CORE_DIR / "thinking_os"

for _p in (_THINKING_OS_DIR, _CORE_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
