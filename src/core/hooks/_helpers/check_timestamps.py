"""Warn-tier detector for timestamp forms that silently store the wrong instant.

Reads pending source on stdin, prints one warning line per finding to stdout,
and always exits 0 — the caller decides what to do with the text. Python is
parsed with the AST because `fromtimestamp(float(x), tz=UTC)` defeats any regex
lookahead that stops at the first `)`; shell is matched by line.

The forms flagged here raise nothing at runtime: they parse, insert and render,
then drop records from a filter or show a view hours behind. Contract:
docs/engineering/timestamp-contract.md.
"""

from __future__ import annotations

import ast
import re
import sys

ALLOW_MARKER = "ts-allow"

BANNED_CALLS = {
    "utcnow": ("naive despite the name; deprecated in 3.12", "datetime.now(timezone.utc)"),
    "utcfromtimestamp": (
        "naive; deprecated alongside utcnow",
        "datetime.fromtimestamp(x, tz=timezone.utc)",
    ),
}

LOCAL_DAY_IN_SHELL = re.compile(r"date\s+\+%Y-%m-%d\b")


def _attr_name(node: ast.AST) -> str:
    return node.attr if isinstance(node, ast.Attribute) else getattr(node, "id", "")


def _allowed_lines(source: str) -> set[int]:
    return {n for n, line in enumerate(source.splitlines(), 1) if ALLOW_MARKER in line}


def collect_python_warnings(source: str) -> list[str]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    allowed = _allowed_lines(source)
    warnings = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or node.lineno in allowed:
            continue
        name = _attr_name(node.func)

        if name in BANNED_CALLS:
            why, fix = BANNED_CALLS[name]
            warnings.add(f"  line {node.lineno}: `{name}()` is {why}. Use `{fix}`.")

        elif name == "fromtimestamp" and not any(kw.arg == "tz" for kw in node.keywords):
            warnings.add(
                f"  line {node.lineno}: `fromtimestamp()` without `tz=` renders a UTC "
                "epoch in the server's local zone. Use `tz=timezone.utc`."
            )

        elif name == "now" and not node.args and not node.keywords:
            warnings.add(
                f"  line {node.lineno}: `datetime.now()` is naive local — wrong on any "
                "machine outside UTC and twice a year under DST. Use "
                "`datetime.now(timezone.utc)`."
            )

        elif name == "mktime" and node.args:
            inner = node.args[0]
            if isinstance(inner, ast.Call) and _attr_name(inner.func) == "strptime":
                warnings.add(
                    f"  line {node.lineno}: `mktime(strptime(...))` treats a parsed UTC "
                    "struct as local — the documented 3-4h Hub drift. Use "
                    "`calendar.timegm(...)`."
                )

        elif name == "replace" and any(kw.arg == "tzinfo" for kw in node.keywords):
            warnings.add(
                f"  line {node.lineno}: `.replace(tzinfo=...)` OVERWRITES an existing "
                "offset instead of converting it. Guard with `if dt.tzinfo is None:`, "
                "or use `.astimezone(timezone.utc)`."
            )

    return sorted(warnings)


def collect_shell_warnings(source: str) -> list[str]:
    warnings = []
    for lineno, line in enumerate(source.splitlines(), 1):
        if ALLOW_MARKER in line or line.lstrip().startswith("#"):
            continue
        if LOCAL_DAY_IN_SHELL.search(line):
            warnings.append(
                f"  line {lineno}: `date +%Y-%m-%d` is the LOCAL day; it disagrees with "
                "the UTC day for several hours every night. Use `date -u +%Y-%m-%d`."
            )
    return warnings


def main() -> int:
    source = sys.stdin.read()
    is_shell = len(sys.argv) > 1 and sys.argv[1] == "--shell"
    warnings = collect_shell_warnings(source) if is_shell else collect_python_warnings(source)
    if warnings:
        print("Timestamp forms that silently store the wrong instant (Rule 28):")
        print("\n".join(warnings))
        print("  Contract: docs/engineering/timestamp-contract.md")
        print(f"  Intentional? end the line with a `{ALLOW_MARKER}: <why>` comment.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
