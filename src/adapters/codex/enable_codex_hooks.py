#!/usr/bin/env python3
"""Idempotently enable Codex's `hooks = true` feature flag.

Usage:
    python3 enable_codex_hooks.py <path-to-config.toml>

Emits one stdout line describing what happened and exits 0:
    "already enabled in <path>"
    "enabled in <path>"

Why this lives in a standalone file instead of a `$(python3 - <<'PY' …)`
heredoc inside adapters/codex/install.sh: the heredoc form has been
observed to hang forever when install.sh runs through a hook-wrapped
Bash tool (the capturing pipe blocks on EOF under the nested shell
layers). Invoking python3 with a script argument uses normal argv +
file IO — no pipe capture around a heredoc — and completes reliably.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

SECTION_RE = re.compile(r"(?ms)^\[features\]\s*\n(?P<body>.*?)(?=^\[|\Z)")
TRUE_RE = re.compile(r"(?m)^[ \t]*hooks[ \t]*=[ \t]*true[ \t]*$")
FALSE_RE = re.compile(r"(?m)^[ \t]*hooks[ \t]*=[ \t]*false[ \t]*$")
LEGACY_RE = re.compile(r"(?m)^[ \t]*codex_hooks[ \t]*=[ \t]*(?:true|false)[ \t]*\n?")
OBSOLETE_RE = re.compile(r"(?m)^[ \t]*rmcp_client[ \t]*=[ \t]*(?:true|false)[ \t]*\n?")


def _status(path: Path, enabled: bool) -> str:
    verb = "enabled" if enabled else "already enabled"
    return f"{verb} in {path}"


def _finish_body(body: str, has_next_section: bool) -> str:
    body = body.strip("\n")
    if not body.strip():
        return ""
    return body + ("\n\n" if has_next_section else "\n")


def _update(path: Path, text: str) -> tuple[str, str]:
    """Return (new_text, status_message). Pure — no IO."""
    match = SECTION_RE.search(text)
    if match:
        old_body = match.group("body")
        body = OBSOLETE_RE.sub("", LEGACY_RE.sub("", old_body))
        has_next_section = match.end("body") < len(text)
        if TRUE_RE.search(body):
            body = _finish_body(body, has_next_section)
            if body == old_body:
                return text, _status(path, enabled=False)
            new_text = text[: match.start("body")] + body + text[match.end("body") :]
            return new_text, _status(path, enabled=True)
        if FALSE_RE.search(body):
            body = FALSE_RE.sub("hooks = true", body, count=1)
        else:
            body = body.rstrip("\n")
            if body:
                body += "\n"
            body += "hooks = true"
        body = _finish_body(body, has_next_section)
        if body == old_body:
            return text, _status(path, enabled=False)
        new_text = text[: match.start("body")] + body + text[match.end("body") :]
        return new_text, _status(path, enabled=True)

    if text and not text.endswith("\n"):
        text += "\n"
    if text:
        text += "\n"
    text += "[features]\nhooks = true\n"
    return text, _status(path, enabled=True)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: enable_codex_hooks.py <config.toml>", file=sys.stderr)
        return 64

    path = Path(argv[1])
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    new_text, status = _update(path, text)
    if new_text != text:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(new_text, encoding="utf-8")
    print(status)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
