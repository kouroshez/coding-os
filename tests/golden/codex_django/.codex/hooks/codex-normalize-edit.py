#!/usr/bin/env python3

from __future__ import annotations

import json
import re
import sys
from typing import Any

_FILE_HEADER = re.compile(r"^\*\*\* (?:Add|Update|Delete) File: (.+)$")
_MOVE_HEADER = re.compile(r"^\*\*\* Move to: (.+)$")


def _patch_files(command: str) -> dict[str, dict[str, list[str]]]:
    files: dict[str, dict[str, list[str]]] = {}
    paths: list[str] = []
    added: list[str] = []
    removed: list[str] = []

    def flush() -> None:
        for path in paths:
            entry = files.setdefault(path, {"added": [], "removed": []})
            entry["added"].extend(added)
            entry["removed"].extend(removed)

    for line in command.splitlines():
        file_match = _FILE_HEADER.match(line)
        if file_match:
            flush()
            paths = [file_match.group(1).strip()]
            added = []
            removed = []
            continue
        move_match = _MOVE_HEADER.match(line)
        if move_match and paths:
            paths.append(move_match.group(1).strip())
            continue
        if not paths:
            continue
        if line.startswith("+"):
            added.append(line[1:])
        elif line.startswith("-"):
            removed.append(line[1:])
    flush()
    return files


def normalize(payload: dict[str, Any]) -> list[dict[str, Any]]:
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        raise ValueError("Codex edit payload has no tool_input object")

    command = tool_input.get("command")
    if isinstance(command, str) and command.strip():
        files = _patch_files(command)
    else:
        file_path = tool_input.get("file_path")
        files = {str(file_path): {"added": [], "removed": []}} if file_path else {}
    if not files:
        raise ValueError("Codex edit payload contains no affected file path")

    normalized: list[dict[str, Any]] = []
    for file_path, changes in files.items():
        item = dict(payload)
        normalized_input = dict(tool_input)
        new_string = "\n".join(changes["added"])
        normalized_input.update(
            {
                "file_path": file_path,
                "old_string": "\n".join(changes["removed"]),
                "new_string": new_string,
                "content": new_string,
            }
        )
        item["tool_name"] = "Edit"
        item["tool_input"] = normalized_input
        normalized.append(item)
    return normalized


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("Codex hook payload must be a JSON object")
        for item in normalize(payload):
            json.dump(item, sys.stdout, ensure_ascii=False, separators=(",", ":"))
            sys.stdout.write("\n")
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
