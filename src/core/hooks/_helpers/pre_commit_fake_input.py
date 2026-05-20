#!/usr/bin/env python3
"""Emit a Write-tool-shaped JSON envelope for a staged file.

Used by .git/hooks/pre-commit to feed core/hooks/block-*.sh scripts as
if Claude/Codex had issued the Write. Extracted to a stand-alone module
because bash 5.3.9 deadlocks when `python3 -c '<multiline>'` is invoked
inside `$(...)` command substitution (see commit 8668caf for the same
fix on intent-primer.sh).

Usage: python3 pre_commit_fake_input.py <abs_path> <repo_relative_path>
"""

from __future__ import annotations

import json
import sys


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: pre_commit_fake_input.py <abs_path> <file_path>", file=sys.stderr)
        return 2
    abs_path, file_path = sys.argv[1], sys.argv[2]
    try:
        with open(abs_path, "r", errors="replace") as f:
            content = f.read()
    except Exception:
        content = ""
    payload = {
        "tool_name": "Write",
        "tool_input": {
            "file_path": file_path,
            "content": content,
            "new_string": content,
        },
    }
    json.dump(payload, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
