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


def _resolve_cos_bin() -> str:
    """Locate the `cos` entrypoint for the daemon to invoke."""
    import shutil

    which = shutil.which("cos")
    if which:
        return which
    return sys.argv[0]
