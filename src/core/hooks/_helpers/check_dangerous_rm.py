"""Detect a recursive `rm` targeting a critical path. stdin: hook JSON envelope.

Prints `block` or `allow` to stdout (the Bash hook maps block→exit 2). A
shlex-correct parser replaces the old `rm -rf …\\b` regex, which let
`rm -rf /`, `rm -rf .`, `rm -rf ..`, `rm -rf *` and flag-order variants
(`-fr`, `-r -f`) slip through because the trailing word-boundary never matched
a symbol target.
"""

from __future__ import annotations

import json
import re
import shlex
import sys

_DANGEROUS = {"/", ".", "..", "./", "../", "~", "~/", "*", "/*", "$HOME", "${HOME}"}
_DANGEROUS_DIRS = {"backend", "frontend", "docs", "infrastructure"}
_WRAPPERS = {"sudo", "command", "env", "nice", "ionice", "time"}


def _is_dangerous_target(tok: str) -> bool:
    t = tok.strip()
    if t in _DANGEROUS:
        return True
    base = t.rstrip("/")
    if base in _DANGEROUS_DIRS or base in {f"./{d}" for d in _DANGEROUS_DIRS}:
        return True
    # Top-level absolute dir (e.g. /etc, /usr) — one slash, more than just "/".
    if t.startswith("/") and t.count("/") == 1 and len(t) > 1:
        return True
    return False


def _is_recursive(flags: list[str]) -> bool:
    for f in flags:
        if f == "--recursive":
            return True
        if f.startswith("--"):
            continue  # other long option — never implies recursion
        if "r" in f or "R" in f:  # short bundle: -r, -rf, -fr, -Rf …
            return True
    return False


def _segment_is_dangerous(segment: str) -> bool:
    try:
        toks = shlex.split(segment)
    except ValueError:
        return False
    while toks and toks[0] in _WRAPPERS:
        toks = toks[1:]
    if not toks or toks[0] != "rm":
        return False
    flags = [t for t in toks[1:] if t.startswith("-")]
    targets = [t for t in toks[1:] if not t.startswith("-")]
    if not _is_recursive(flags):
        return False
    return any(_is_dangerous_target(t) for t in targets)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        print("allow")
        return 0
    command = (payload.get("tool_input", {}) or {}).get("command", "") or ""
    for segment in re.split(r"(?:&&|\|\||;|\||\n)", command):
        segment = segment.strip()
        if segment and _segment_is_dangerous(segment):
            print("block")
            return 0
    print("allow")
    return 0


if __name__ == "__main__":
    sys.exit(main())
