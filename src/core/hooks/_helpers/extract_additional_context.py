#!/usr/bin/env python3
"""Extract the inner additionalContext text from a hook's JSON stdout.

Codex/Cursor dispatchers coalesce several delegate hooks into one
SessionStart response. The delegates are the SAME scripts Claude runs, and
many emit a Claude-style envelope on stdout:

    {"hookSpecificOutput": {"hookEventName": "SessionStart",
                            "additionalContext": "<card text>"}}

Concatenating that raw envelope into the dispatcher's own additionalContext
would surface literal JSON to the agent. This filter unwraps it: when stdin
parses as such an envelope it prints only the inner text; otherwise it passes
the raw bytes through unchanged (plain-text cards, stderr warnings, empty).
"""

from __future__ import annotations

import json
import sys


def _inner_context(obj: object) -> str | None:
    if not isinstance(obj, dict):
        return None
    hso = obj.get("hookSpecificOutput")
    if isinstance(hso, dict) and "additionalContext" in hso:
        return str(hso["additionalContext"])
    if "additionalContext" in obj:
        return str(obj["additionalContext"])
    if "additional_context" in obj:
        return str(obj["additional_context"])
    return None


def main() -> int:
    raw = sys.stdin.read()
    if not raw.strip():
        return 0
    try:
        obj = json.loads(raw)
    except (ValueError, TypeError):
        sys.stdout.write(raw)
        return 0
    ctx = _inner_context(obj)
    sys.stdout.write(raw if ctx is None else ctx)
    return 0


if __name__ == "__main__":
    sys.exit(main())
