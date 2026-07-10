#!/usr/bin/env python3

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def _consume(value: Any, contexts: list[str], reasons: list[str]) -> tuple[bool, bool]:
    if not isinstance(value, dict):
        return False, False
    blocked = value.get("decision") == "block"
    recognized = blocked
    if blocked and isinstance(value.get("reason"), str):
        reasons.append(value["reason"].strip())
    specific = value.get("hookSpecificOutput")
    candidates = [specific, value] if isinstance(specific, dict) else [value]
    for candidate in candidates:
        for key in ("additionalContext", "additional_context"):
            if key not in candidate:
                continue
            recognized = True
            context = candidate[key]
            if isinstance(context, str) and context.strip():
                contexts.append(context.strip())
            break
    return blocked, recognized


def merge(event: str, paths: list[str]) -> dict[str, Any]:
    contexts: list[str] = []
    reasons: list[str] = []
    blocked = False
    for raw_path in paths:
        text = Path(raw_path).read_text(encoding="utf-8", errors="replace").strip()
        if not text:
            continue
        try:
            value = json.loads(text)
        except (TypeError, ValueError):
            contexts.append(text)
            continue
        is_blocked, recognized = _consume(value, contexts, reasons)
        blocked = blocked or is_blocked
        if isinstance(value, dict) and value and not recognized:
            contexts.append(text)

    output: dict[str, Any] = {}
    if contexts:
        output["hookSpecificOutput"] = {
            "hookEventName": event,
            "additionalContext": "\n".join(dict.fromkeys(contexts)),
        }
    if blocked:
        output["decision"] = "block"
        output["reason"] = "\n".join(dict.fromkeys(filter(None, reasons))) or "Hook blocked"
    return output


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: codex-merge-hook-output.py EVENT [OUTPUT_FILE ...]", file=sys.stderr)
        return 2
    json.dump(merge(argv[1], argv[2:]), sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
