#!/usr/bin/env python3
"""Ensure Codex's project identity and `mcp_servers.coding-os` config are correct.

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
SHELL_SET_RE = re.compile(r"(?ms)^\[shell_environment_policy\.set\]\s*\n(?P<body>.*?)(?=^\[|\Z)")
IDENTITY_KEYS = {"COS_AGENT", "COS_STATE_DIR", "COS_AGENT_DIR"}


def _quote(value: str) -> str:
    """Render a TOML-safe basic string."""
    return json.dumps(value, ensure_ascii=False)


def _render_section(command: str, args: list[str], project_root: Path) -> str:
    state_dir = project_root / ".coding-os"
    agent_dir = state_dir / "codex"
    lines = [
        "[mcp_servers.coding-os]",
        f"command = {_quote(command)}",
        "args = [" + ", ".join(_quote(arg) for arg in args) + "]",
        "env = { "
        f"COS_AGENT = {_quote('codex')}, "
        f"COS_STATE_DIR = {_quote(str(state_dir))}, "
        f"COS_AGENT_DIR = {_quote(str(agent_dir))} "
        "}",
    ]
    return "\n".join(lines) + "\n"


def _render_shell_set(project_root: Path, preserved: list[str] | None = None) -> str:
    state_dir = project_root / ".coding-os"
    lines = [
        "[shell_environment_policy.set]",
        f"COS_AGENT = {_quote('codex')}",
        f"COS_STATE_DIR = {_quote(str(state_dir))}",
        f"COS_AGENT_DIR = {_quote(str(state_dir / 'codex'))}",
    ]
    lines.extend(preserved or [])
    return "\n".join(lines).rstrip() + "\n"


def _update_shell_set(text: str, project_root: Path) -> str:
    match = SHELL_SET_RE.search(text)
    preserved: list[str] = []
    if match:
        for line in match.group("body").splitlines():
            key = line.split("=", 1)[0].strip() if "=" in line else ""
            if key not in IDENTITY_KEYS:
                preserved.append(line)
    section = _render_shell_set(project_root, preserved)
    return _update_section(text, section, SHELL_SET_RE)


def _status(path: Path, configured: bool) -> str:
    verb = "configured" if configured else "already configured"
    return f"{verb} in {path}"


def _update_section(text: str, section: str, pattern: re.Pattern[str]) -> str:
    matches = list(pattern.finditer(text))
    if matches:
        first = matches[0]
        before = text[: first.start()].rstrip("\n")
        after = pattern.sub("", text[first.end() :]).lstrip("\n")
        pieces = []
        if before:
            pieces.append(before)
        pieces.append(section.rstrip("\n"))
        if after:
            pieces.append(after.rstrip("\n"))
        return "\n\n".join(pieces) + "\n"

    if text and not text.endswith("\n"):
        text += "\n"
    if text:
        text += "\n"
    return text + section


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
    project_root = path.parent.parent.resolve()

    text = path.read_text(encoding="utf-8") if path.exists() else ""
    new_text = _update_shell_set(text, project_root)
    new_text = _update_section(
        new_text,
        _render_section(command, args, project_root),
        SECTION_RE,
    )
    status = _status(path, configured=new_text != text)
    if new_text != text:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(new_text, encoding="utf-8")
    print(status)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
