#!/usr/bin/env python3
"""Scan stdin content for hardcoded stack/adapter literals in cli/*.py.

The forbidden set is data-driven: discovered from templates/*/stack.yaml::id
and adapters/*/adapter.yaml::id (no hardcoded list here either), falling back
to a conservative built-in set when the registries can't be loaded (keeps the
hook useful during bootstrap). Prints violations to stderr, exits 2 on block.

This is the SINGLE source Rule-11 enforcement shares: the PreToolUse hook
(block-hardcoded-literals.sh) AND the rear-guard test (test_no_hardcoded_stacks.py)
both import discover_literals() + scan() from here, so the front and rear guards
can never diverge (R11/F12, TASK-441). The set is NARROWED twice to stay
false-positive-free on cli/*.py: skill names are excluded (they collide with
path segments and dict keys — e.g. "thinking_os", "observability"), and a small
set of stack ids that double as ordinary code tokens is excluded (AMBIGUOUS_IDS).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent

CONTEXTUAL_ALLOW_RE = [
    re.compile(r"^\s*#"),
    re.compile(r'^\s*"""'),
    re.compile(r"^\s*'"),
    re.compile(r"^\s*\*"),
]

# Used only when the YAML registries can't be read (bootstrap / no pyyaml).
# Unambiguous stack/adapter ids only — no skills, no AMBIGUOUS_IDS.
BUILTIN_FALLBACK = {
    "django",
    "nextjs",
    "go-fiber",
    "claude",
    "codex",
}

# Stack ids that are also ordinary code tokens, so flagging them as quoted
# literals in cli/*.py is almost always a false positive — never a real
# Rule-11 breach. Excluded from the forbidden set (the rear-guard test would
# otherwise red on legitimate code, and the live hook would block it):
#   go      — the Go binary name, "go.mod" marker, help-string examples
#   python  — the Python binary name, "pyproject.toml" marker
#   meta    — the cos_* response-envelope `meta` field (.get("meta"))
#   fastapi — the pip package / framework name in descriptions
AMBIGUOUS_IDS = {"go", "python", "meta", "fastapi"}


def discover_literals() -> set[str]:
    """Read stack/adapter IDs from stack.yaml + adapter.yaml so the guard stays
    data-driven. Skills are NOT included (Rule 11 is about stack/adapter ids, and
    skill names collide with code), and AMBIGUOUS_IDS are filtered out."""
    result: set[str] = set()
    templates_dir = REPO_ROOT / "src" / "templates"
    adapters_dir = REPO_ROOT / "src" / "adapters"
    try:
        import yaml  # type: ignore
    except ImportError:
        return BUILTIN_FALLBACK
    for stack_yaml in templates_dir.glob("*/stack.yaml"):
        try:
            data = yaml.safe_load(stack_yaml.read_text(encoding="utf-8")) or {}
            sid = data.get("id")
            if sid:
                result.add(str(sid))
        except Exception:  # pragma: no cover - defensive
            continue
    for adapter_yaml in adapters_dir.glob("*/adapter.yaml"):
        try:
            data = yaml.safe_load(adapter_yaml.read_text(encoding="utf-8")) or {}
            aid = data.get("id")
            if aid:
                result.add(str(aid))
        except Exception:  # pragma: no cover - defensive
            continue
    return (result - AMBIGUOUS_IDS) or BUILTIN_FALLBACK


def scan(content: str, forbidden: set[str]) -> list[tuple[int, str, str]]:
    """Return list of (line_no, token, stripped_line) violations."""
    violations: list[tuple[int, str, str]] = []
    patterns = {
        token: re.compile(rf'(?<![A-Za-z0-9_])["\']({re.escape(token)})["\'](?![A-Za-z0-9_])')
        for token in forbidden
    }
    for i, line in enumerate(content.splitlines(), start=1):
        if any(rx.match(line) for rx in CONTEXTUAL_ALLOW_RE):
            continue
        stripped = line.strip()
        for token, patt in patterns.items():
            if patt.search(stripped):
                violations.append((i, token, stripped))
    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", required=True, help="path of the file being edited")
    args = parser.parse_args()

    content = sys.stdin.read()
    if not content:
        return 0

    forbidden = discover_literals()
    violations = scan(content, forbidden)

    if not violations:
        return 0

    print(
        f"BLOCKED: hardcoded stack/adapter literal(s) in {args.file}",
        file=sys.stderr,
    )
    for line_no, token, line in violations[:5]:
        print(f"  line {line_no}: {token!r} → {line[:80]}", file=sys.stderr)
    if len(violations) > 5:
        print(f"  ... and {len(violations) - 5} more", file=sys.stderr)
    print(
        "  Move the metadata to templates/<stack>/stack.yaml or "
        "adapters/<agent>/adapter.yaml and read it via the registry.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
