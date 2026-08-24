"""Comment-preserving list edits on a project's `.coding-os.yaml`.

A `yaml.dump` round-trip reserializes the whole document and deletes every
comment the operator wrote, so a one-item change is spliced into the text
instead. Spec: docs/engineering/skill-architecture.md § Per-project extras.
"""

from __future__ import annotations

import re

_ITEM_RE = re.compile(r"^(?P<indent>\s*)-\s+(?P<val>.+?)\s*$")
_EMPTY_INLINE_RE = re.compile(r"^[^\s:]+:\s*\[\s*\]\s*(#.*)?$")
_DEFAULT_INDENT = "  "


def _find_header(lines: list[str], key: str) -> int | None:
    pattern = re.compile(rf"^{re.escape(key)}:\s*(\[\s*\]\s*)?(#.*)?$")
    for i, line in enumerate(lines):
        if pattern.match(line.rstrip("\n")):
            return i
    return None


def _last_item(lines: list[str], header: int) -> tuple[int, str] | None:
    """Index and indent of the block's final `- item` line, or None if empty."""
    found: tuple[int, str] | None = None
    for j in range(header + 1, len(lines)):
        body = lines[j].rstrip("\n")
        if body.strip() == "" or body.startswith("#"):
            continue
        match = _ITEM_RE.match(body)
        if match is None:
            break
        found = (j, match.group("indent") or _DEFAULT_INDENT)
    return found


def add_list_item(raw: str, key: str, item: str) -> str:
    """Append `item` to the top-level list `key`, creating the block if absent."""
    lines = raw.splitlines(keepends=True)
    header = _find_header(lines, key)
    if header is None:
        suffix = "" if raw == "" or raw.endswith("\n") else "\n"
        return f"{raw}{suffix}{key}:\n{_DEFAULT_INDENT}- {item}\n"

    if _EMPTY_INLINE_RE.match(lines[header].rstrip("\n")):
        lines[header] = f"{key}:\n"

    last = _last_item(lines, header)
    at, indent = (last[0] + 1, last[1]) if last else (header + 1, _DEFAULT_INDENT)
    lines.insert(at, f"{indent}- {item}\n")
    return "".join(lines)


def remove_list_item(raw: str, key: str, item: str) -> str:
    """Drop `item` from the top-level list `key`; a no-op when it is absent.

    Removing the block's last item drops the now-empty `key:` header too, so an
    add/remove pair leaves the file byte-identical instead of accreting a bare
    key. Absent and empty read the same to every consumer (`… or []`).
    """
    lines = raw.splitlines(keepends=True)
    header = _find_header(lines, key)
    if header is None:
        return raw
    for j in range(header + 1, len(lines)):
        body = lines[j].rstrip("\n")
        if body.strip() == "" or body.startswith("#"):
            continue
        match = _ITEM_RE.match(body)
        if match is None:
            break
        if match.group("val").strip().strip("'\"") == item:
            del lines[j]
            break
    if _last_item(lines, header) is None and lines[header].rstrip("\n") == f"{key}:":
        del lines[header]
    return "".join(lines)
