"""thinking_os test fixtures.

Puts core/thinking_os on sys.path so tests using bare imports
(``from cognition import ...``, ``from database import ...``) resolve the
same way the MCP server does at runtime. Without this conftest,
``pytest core/thinking_os/tests/`` collects but cannot import these
modules and aborts with ModuleNotFoundError. Mirrors the pattern in
core/graph_os/tests/conftest.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

_THINKING_OS_DIR = Path(__file__).resolve().parent.parent

if str(_THINKING_OS_DIR) not in sys.path:
    sys.path.insert(0, str(_THINKING_OS_DIR))
if str(_THINKING_OS_DIR.parent) not in sys.path:
    sys.path.insert(0, str(_THINKING_OS_DIR.parent))
