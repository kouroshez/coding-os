#!/usr/bin/env python3
"""Ensure Codex's `mcp_servers.coding-os` config section is correct.

Usage:
    python3 ensure_codex_mcp.py <config.toml> <command> [args...]

Emits one stdout line describing what happened and exits 0:
    "already configured in <path>"
    "configured in <path>"
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SECTION_RE = re.compile(r"(?ms)^\[mcp_servers\.coding-os\]\s*\n.*?(?=^\[|\Z)")


def _quote(value: str) -> str:
    """Render a TOML-safe basic string."""
    return json.dumps(value, ensure_ascii=False)


def _render_section(command: str, args: list[str]) -> str:
    lines = [
        "[mcp_servers.coding-os]",
        f"command = {_quote(command)}",
        "args = [" + ", ".join(_quote(arg) for arg in args) + "]",
    ]
    return "\n".join(lines) + "\n"


def _status(path: Path, configured: bool) -> str:
    verb = "configured" if configured else "already configured"
    return f"{verb} in {path}"


def _update(path: Path, text: str, section: str) -> tuple[str, str]:
    matches = list(SECTION_RE.finditer(text))
    if matches:
        first = matches[0]
        before = text[: first.start()].rstrip("\n")
        after = SECTION_RE.sub("", text[first.end() :]).lstrip("\n")
        pieces = []
        if before:
            pieces.append(before)
        pieces.append(section.rstrip("\n"))
        if after:
            pieces.append(after.rstrip("\n"))
        new_text = "\n\n".join(pieces) + "\n"
        status = _status(path, configured=new_text != text)
        return new_text, status

    if text and not text.endswith("\n"):
        text += "\n"
    if text:
        text += "\n"
    return text + section, _status(path, configured=True)


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(
            "usage: ensure_codex_mcp.py <config.toml> <command> [args...]",
            file=sys.stderr,
        )
        return 64

    path = Path(argv[1])
    command = argv[2]
    args = argv[3:]

    text = path.read_text(encoding="utf-8") if path.exists() else ""
    new_text, status = _update(path, text, _render_section(command, args))
    if new_text != text:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(new_text, encoding="utf-8")
    print(status)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
