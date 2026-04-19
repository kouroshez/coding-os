#!/usr/bin/env python3
"""Idempotently enable Codex's `codex_hooks = true` feature flag.

Usage:
    python3 enable_codex_hooks.py <path-to-config.toml>

Emits one stdout line describing what happened and exits 0:
    "already enabled in ~/.codex/config.toml"
    "enabled in ~/.codex/config.toml"
    "config path missing — nothing to do"

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
TRUE_RE = re.compile(r"(?m)^[ \t]*codex_hooks[ \t]*=[ \t]*true[ \t]*$")
FALSE_RE = re.compile(r"(?m)^[ \t]*codex_hooks[ \t]*=[ \t]*false[ \t]*$")


def _update(text: str) -> tuple[str, str]:
    """Return (new_text, status_message). Pure — no IO."""
    match = SECTION_RE.search(text)
    if match:
        body = match.group("body")
        if TRUE_RE.search(body):
            return text, "already enabled in ~/.codex/config.toml"
        if FALSE_RE.search(body):
            body = FALSE_RE.sub("codex_hooks = true", body, count=1)
        else:
            if body and not body.endswith("\n"):
                body += "\n"
            body += "codex_hooks = true\n"
        new_text = text[: match.start("body")] + body + text[match.end("body") :]
        return new_text, "enabled in ~/.codex/config.toml"

    if text and not text.endswith("\n"):
        text += "\n"
    if text:
        text += "\n"
    text += "[features]\ncodex_hooks = true\n"
    return text, "enabled in ~/.codex/config.toml"


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: enable_codex_hooks.py <config.toml>", file=sys.stderr)
        return 64

    path = Path(argv[1])
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    new_text, status = _update(text)
    if new_text != text:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(new_text, encoding="utf-8")
    print(status)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
