"""Detect destructive `git reset --hard` / `git clean -f` for block-dangerous-commands.sh.

git resolves ANY unambiguous long-option prefix, so the old bash greps —
literal `git reset --hard` and `git clean\\s+-[a-z]*f` — were bypassable by
abbreviation (`reset --har`, `clean --for`, `clean --f`) and by splitting the
short cluster (`clean -d -f`). This tokenizes via the shared parser and matches
options by SHAPE so every abbreviation/split that git accepts is caught, while a
non-force `git clean -n` (dry-run) and unrelated flags stay allowed.

stdin: hook JSON envelope. Prints one verdict token: `reset-hard`,
`clean-force`, or `allow`. Never raises — any parse error prints `allow`
(branch-guard is the fail-closed twin for the HEAD-moving reset).
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from git_command_parse import abbrev_resolves, git_invocations

# Competitor long options for prefix disambiguation. `git reset --hard` has no
# other `--ha*` option, so `--ha`/`--har` resolve to it; `git clean --force`
# has no other `--f*`, so `--f`/`--fo` resolve to it.
_RESET_LONGS = frozenset({"--soft", "--mixed", "--hard", "--merge", "--keep", "--patch", "--quiet"})
_CLEAN_LONGS = frozenset({"--force", "--dry-run", "--quiet", "--exclude", "--interactive"})


def _reset_is_hard(args: list[str]) -> bool:
    for a in args:
        if a == "--":
            break  # pathspec separator — no flags after it
        if a.startswith("--") and abbrev_resolves(a, "--hard", _RESET_LONGS):
            return True
    return False


def _clean_is_force(args: list[str]) -> bool:
    for a in args:
        if a == "--":
            break
        if a.startswith("--"):
            if abbrev_resolves(a, "--force", _CLEAN_LONGS):
                return True
        elif len(a) >= 2 and a[0] == "-" and a[1:].isalpha() and "f" in a[1:]:
            return True  # short cluster carrying -f: `-f`, `-fd`, `-df`, split `-d -f`
    return False


def _verdict(command: str) -> str:
    for inv in git_invocations(command):
        if inv.subcmd == "reset" and _reset_is_hard(inv.args):
            return "reset-hard"
        if inv.subcmd == "clean" and _clean_is_force(inv.args):
            return "clean-force"
    return "allow"


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        command = (payload.get("tool_input", {}) or {}).get("command", "") or ""
    except (json.JSONDecodeError, ValueError, AttributeError):
        print("allow")
        return 0
    if not isinstance(command, str) or not command:
        print("allow")
        return 0
    print(_verdict(command))
    return 0


if __name__ == "__main__":
    sys.exit(main())
