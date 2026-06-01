"""Advance the active role (.role) along the composed chain by work phase.

Called by advance-role.sh (PostToolUse). Maps the tool just used to a work
phase and asks roles_state.advance_role to set .role to the chain member that
best matches — so the banner's roles= field reflects what the agent is DOING
(analyze → build → verify), not a frozen chain lead (TASK-057 F2.3).

Prints the new active role (for the hook log); prints nothing on no-op.

USAGE
    python3 advance_role.py <tool_name> <target_dir> [bash_command]
"""

from __future__ import annotations

import logging
import re
import sys
from pathlib import Path

logger = logging.getLogger("advance_role")

_THIS = Path(__file__).resolve()
_THINKING_OS = _THIS.parents[2] / "thinking_os"
if _THINKING_OS.is_dir() and str(_THINKING_OS) not in sys.path:
    sys.path.insert(0, str(_THINKING_OS))

# Bash commands that signal a verification phase (tests, linters, type checks).
_VERIFY_CMD = re.compile(
    r"\b(pytest|jest|vitest|go test|make (?:verify|test)|"
    r"npm test|ruff|mypy|eslint|tsc|coverage|verify-hooks)\b"
)


def _phase_for(tool: str, command: str) -> str | None:
    if tool in ("Write", "Edit", "MultiEdit"):
        # A doc/markdown write is a documentation phase; code is build.
        return "edit"
    if tool == "Bash" and command and _VERIFY_CMD.search(command):
        return "verify"
    return None


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        return 0
    tool = argv[1] or ""
    target_dir = argv[2] or None
    command = argv[3] if len(argv) > 3 else ""

    phase = _phase_for(tool, command)
    if phase is None:
        return 0

    try:
        import roles_state
    except ImportError as exc:
        logger.debug("roles_state import unavailable: %s", exc)
        return 0

    chosen = roles_state.advance_role(phase, target_dir)
    if chosen:
        print(chosen)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
