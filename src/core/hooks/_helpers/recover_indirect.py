"""Recover indirection-hidden git commands for block-dangerous-commands.sh.

stdin: hook JSON envelope. Prints each recovered inner command (from
eval / pipe-into-sh / here-string / xargs git) on its own line so the Bash gate
can re-scan them with its existing force-push / reset / clean greps. Never
raises — any error prints nothing (branch_guard is the fail-closed twin for the
protected ops). See git_command_parse.recover_indirect_commands.
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from git_command_parse import recover_indirect_commands


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        command = (payload.get("tool_input", {}) or {}).get("command", "") or ""
    except (json.JSONDecodeError, ValueError, AttributeError):
        return 0
    if not isinstance(command, str) or not command:
        return 0
    for line in recover_indirect_commands(command):
        sys.stdout.write(line + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
