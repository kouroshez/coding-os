"""Extract a string field from a hook JSON envelope on stdin.

python3 fallback for the `cos_json_field` Bash helper when jq is absent.
argv = one or more dotted paths (e.g. ``tool_input.command``); prints the
first non-empty value found, else nothing. Never raises — a parse failure
prints nothing and exits 0, so the only fail-closed path is the Bash
caller's `cos_require_parser` guard (which runs outside command-substitution
where an exit can actually block).
"""

from __future__ import annotations

import json
import sys


def _dig(obj: object, dotted: str) -> object | None:
    cur = obj
    for part in dotted.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError, UnicodeDecodeError):
        return 0
    for path in sys.argv[1:]:
        value = _dig(data, path)
        if value not in (None, ""):
            sys.stdout.write(value if isinstance(value, str) else json.dumps(value))
            return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
