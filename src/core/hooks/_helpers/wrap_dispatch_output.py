#!/usr/bin/env python3
"""Wrap captured dispatch output in the JSON envelope Codex/Cursor expect.

Replaces inline `python3 - <<'PY'` heredocs in adapter dispatch shell
scripts (Rule 8: heredoc inside `$(...)` deadlocks bash 5.x).

Two output shapes:

    --shape additional-context <event_name> <captured_file>
        {"hookSpecificOutput": {"hookEventName": "<event>",
                                "additionalContext": "<captured>"}}

    --shape user-message <max_chars> <captured_file>
        {"user_message": "<captured truncated to max_chars>"}

    --shape additional-context-flat <captured_file>
        {"additional_context": "<captured>"}    # Cursor snake_case
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

USAGE = (
    "usage:\n"
    "  wrap_dispatch_output.py additional-context <event_name> <captured_file>\n"
    "  wrap_dispatch_output.py user-message <max_chars> <captured_file>\n"
)


def _read_text(path_str: str) -> str:
    p = Path(path_str)
    return p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""


def _emit_additional_context(event_name: str, captured_file: str) -> int:
    text = _read_text(captured_file).strip()
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": event_name,
                "additionalContext": text,
            }
        },
        sys.stdout,
        ensure_ascii=False,
    )
    sys.stdout.write("\n")
    return 0


def _emit_additional_context_flat(captured_file: str) -> int:
    """Cursor sessionStart schema: flat `additional_context` key."""
    text = _read_text(captured_file).strip()
    json.dump({"additional_context": text}, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


def _emit_user_message(max_chars_s: str, captured_file: str) -> int:
    try:
        max_chars = int(max_chars_s)
    except ValueError:
        print(f"max_chars must be an integer: {max_chars_s!r}", file=sys.stderr)
        return 2
    text = _read_text(captured_file).strip()
    if len(text) > max_chars:
        text = text[: max(0, max_chars - 3)] + "..."
    out: dict[str, str] = {}
    if text:
        out["user_message"] = text
    json.dump(out, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        sys.stderr.write(USAGE)
        return 2
    shape = argv[1]
    if shape == "additional-context" and len(argv) == 4:
        return _emit_additional_context(argv[2], argv[3])
    if shape == "additional-context-flat" and len(argv) == 3:
        return _emit_additional_context_flat(argv[2])
    if shape == "user-message" and len(argv) == 4:
        return _emit_user_message(argv[2], argv[3])
    sys.stderr.write(USAGE)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
