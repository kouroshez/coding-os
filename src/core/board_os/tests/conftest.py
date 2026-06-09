"""board_os test fixtures.

Adds the repo root to sys.path so tests using `from core.board_os …`
imports resolve when invoked via the matrix command (`pytest
core/board_os/tests/`). Mirrors core/thinking_os/tests/conftest.py.

Also adds src/core/thinking_os so the board_os conn fixture — which runs
the thinking_os DB migrations, including v37's bare `from sanitizer import`
(the thinking_os in-package convention) — resolves in isolation, not only
when a thinking_os test happened to prime sys.path first.
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_THINKING_OS = Path(__file__).resolve().parents[2] / "thinking_os"
if str(_THINKING_OS) not in sys.path:
    sys.path.insert(0, str(_THINKING_OS))
