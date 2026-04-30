"""board_os test fixtures.

Adds the repo root to sys.path so tests using `from core.board_os …`
imports resolve when invoked via the matrix command (`pytest
core/board_os/tests/`). Mirrors core/thinking_os/tests/conftest.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
