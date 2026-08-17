"""Hub daemon file locations and the `cos` binary the service definition invokes.

Imports no sibling, so both `cli.hub_commands` and `cli._hub_service` can build
on it without a cycle.
"""

from __future__ import annotations

import sys
from pathlib import Path

DEFAULT_HUB_PORT = 9188
HUB_HOST = "127.0.0.1"

SERVICE_NAME = "com.coding-os.hub"


def _hub_dir() -> Path:
    d = Path.home() / ".coding-os"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _log_file() -> Path:
    return _hub_dir() / "hub.log"


# The hub daemon appends stdout+stderr to hub.log for weeks at a time. uvicorn's
# access log is off (see web/server.run_server), so steady-state growth is ~zero
# — this cap only backstops a crash-looping handler spewing tracebacks between
# restarts. Truncation keeps the TAIL: the newest lines explain why the hub is
# unhappy now.
HUB_LOG_MAX_BYTES = 8 * 1024 * 1024
_HUB_LOG_KEEP_BYTES = HUB_LOG_MAX_BYTES // 2


def _truncate_hub_log(log: Path) -> int:
    """Trim an oversized hub.log to its tail; return the bytes reclaimed."""
    import os

    try:
        size = log.stat().st_size
    except OSError:
        return 0
    if size <= HUB_LOG_MAX_BYTES:
        return 0
    try:
        with log.open("rb") as handle:
            handle.seek(-_HUB_LOG_KEEP_BYTES, os.SEEK_END)
            tail = handle.read()
        # Drop the partial line the seek landed inside — but only when there IS
        # a later newline. A single traceback line longer than the keep window
        # would otherwise truncate the file to nothing.
        newline = tail.find(b"\n")
        if newline != -1:
            tail = tail[newline + 1 :]
        with log.open("wb") as handle:
            handle.write(tail)
    except OSError:
        return 0
    return size - len(tail)


def _resolve_cos_bin() -> str:
    """Locate the `cos` entrypoint for the daemon to invoke."""
    import shutil

    which = shutil.which("cos")
    if which:
        return which
    return sys.argv[0]
