"""board_os import bridge shared by the Scrumban cos_task_* tool modules.

`core/` is a namespace package without __init__.py, so reaching `board_os`
needs the project root on sys.path. Import failure is not fatal: the flag lets
each tool module skip its registrations and the server still starts without a
board.
"""

from __future__ import annotations

import sys
from pathlib import Path

from _server_runtime import logger

try:
    # `from board_os...` requires the project root (parent of `core/`)
    # on sys.path, since `core/` is a namespace package without __init__.py.
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))
    from board_os import mcp_tools as _board_mcp  # type: ignore

    _BOARD_OS_AVAILABLE = True
except ImportError as _exc:
    logger.warning("board_os MCP tools unavailable: %s", _exc)
    _BOARD_OS_AVAILABLE = False
