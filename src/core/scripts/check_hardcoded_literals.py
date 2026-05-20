#!/usr/bin/env python3
"""Scan stdin content for hardcoded stack/adapter literals in cli/*.py.

Mirrors the logic in tests/test_no_hardcoded_stacks.py so the hook and
the test agree. Prints violations to stderr and exits 2 on block, 0 on
clean.

Literals are read from templates/*/stack.yaml::id and
adapters/*/adapter.yaml::id — no hardcoded list in this file either.
Falls back to a conservative built-in set if the registries can't be
loaded (keeps the hook useful during bootstrap).
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

BUILTIN_FALLBACK = {
    "django",
    "nextjs",
    "fastapi",
    "go",
    "go-fiber",
    "claude",
    "codex",
    "cursor",
    "python-django",
    "nextjs-react",
    "python-fastapi",
    "go-patterns",
    "frontend-design",
}


def discover_literals() -> set[str]:
    """Read IDs from stack.yaml + adapter.yaml so the guard stays data-driven."""
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
            for skill in data.get("skills") or []:
                result.add(str(skill))
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
    return result or BUILTIN_FALLBACK


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
