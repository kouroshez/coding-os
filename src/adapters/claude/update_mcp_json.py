#!/usr/bin/env python3
"""
Coding OS — Claude adapter: idempotent .mcp.json updater.

PURPOSE:
    Add/refresh the `coding-os` entry in a project's .mcp.json. Shipped as
    a standalone script (not a heredoc inside install.sh) because Homebrew
    bash 5.3.9 deadlocks `python3 - <<HEREDOC` setups — sample(1) shows
    `heredoc_write` blocked indefinitely before fork. System /bin/bash
    (3.2) and Linux bash 5.0/5.2 are unaffected, but `#!/usr/bin/env bash`
    resolves to the buggy Homebrew binary on macs that have it. Codex
    adapter ships its updater the same way for the same reason.

USAGE:
    python3 update_mcp_json.py <mcp_file_path> <coding_os_root>

OUTPUT:
    Writes the updated .mcp.json. Exits 0 on success, 1 on bad JSON in
    the existing file.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        sys.stderr.write(
            f"usage: {argv[0]} <mcp_file_path> <coding_os_root>\n"
        )
        return 2

    mcp_path = Path(argv[1])
    cos_root = argv[2]

    # Prefer cos-mcp-start (fast-path entry, ~120ms quicker cold boot)
    # over `cos server-start`. Both are installed by the same wheel, but
    # the fast-path skips cli.main's heavy subcommand imports.
    has_fast = shutil.which("cos-mcp-start") is not None
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
    if has_fast:
        data["mcpServers"]["coding-os"] = {
            "command": "cos-mcp-start",
            "args": [],
        }
    elif has_cos:
        data["mcpServers"]["coding-os"] = {
            "command": "cos",
            "args": ["server-start"],
        }
    else:
        # Fallback before `uv tool install` puts `cos` on PATH. The cwd
        # placeholder lets Cursor/VSCode resolve it per-workspace.
        data["mcpServers"]["coding-os"] = {
            "command": "uv",
            "args": [
                "run",
                "--directory",
                f"{cos_root}/core/thinking_os",
                "python",
                "server.py",
            ],
            "cwd": "${workspaceFolder}",
        }

    with mcp_path.open("w") as f:
        json.dump(data, f, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
