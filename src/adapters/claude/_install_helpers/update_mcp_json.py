#!/usr/bin/env python3
"""
Add/refresh the `coding-os` entry in a project's .mcp.json.

Called from install.sh (form B — separate file, NOT a heredoc) because
Homebrew bash 5.3.9 sporadically deadlocks BOTH `python3 - <<HEREDOC`
AND nested `$(python3 -c "$(cat <<'PY' ... PY)" ...)` inside $(...).
A standalone `.py` invoked as `python3 path/to/file.py args` has no
heredoc surface → no bug.

USAGE:
    python3 update_mcp_json.py <mcp_file> <coding_os_root>

WHEN `cos` IS ON PATH:
    {"command": "cos", "args": ["server-start"]}
WHEN NOT (fresh install before `uv tool install`):
    fallback to absolute `uv run` form anchored at `coding_os_root`.

EXIT
    0 on success (or no-op when JSON would be unchanged).
    1 on bad existing JSON (caller logs WARN; install proceeds).
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        sys.stderr.write(f"usage: {argv[0]} <mcp_file> <coding_os_root>\n")
        return 2

    mcp_path = Path(argv[1])
    cos_root = argv[2]
    has_cos = shutil.which("cos") is not None

    try:
        with mcp_path.open() as f:
            data = json.load(f)
    except FileNotFoundError:
        data = {}
    except json.JSONDecodeError as exc:
        sys.stderr.write(f"  ERROR: {mcp_path} is not valid JSON: {exc}\n")
        return 1

    data.setdefault("mcpServers", {})
    if has_cos:
        data["mcpServers"]["coding-os"] = {
            "command": "cos",
            "args": ["server-start"],
        }
    else:
        data["mcpServers"]["coding-os"] = {
            "command": "uv",
            "args": [
                "run", "--directory", f"{cos_root}/core/thinking_os",
                "python", "server.py",
            ],
            "cwd": "${workspaceFolder}",
        }

    with mcp_path.open("w") as f:
        json.dump(data, f, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
