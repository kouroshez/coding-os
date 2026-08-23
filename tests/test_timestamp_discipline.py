"""Timestamp contract gate: one representation per storage class, UTC at rest.

A wrong timestamp format raises nothing — it parses, inserts and renders, then
silently drops records from a filter or shows a view hours behind. Both have
happened here: `time.mktime` baked the server offset into a UTC epoch ("3-4h
drift on the Hub UI", still documented at `_parse_iso_ts` in
src/core/web/routes/observability.py), and the strict `%Y-%m-%dT%H:%M:%SZ`
readers in logs.py / observability.py reject `.isoformat()` output with a
swallowed ValueError.

So the gate is static, not behavioural: the banned forms may not appear at all.
Contract: docs/engineering/timestamp-contract.md · rule:
src/core/rules/timestamp-discipline.md.
"""

from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

EXCLUDED_PREFIXES = (
    "src/templates/",  # consumer-shipped scaffold; downstream owns style
    "tests/golden/",  # generated snapshots
    "archive/",
)

# Python is scanned with the AST, not a regex: `fromtimestamp(float(x), tz=UTC)`
# defeats any lookahead that stops at the first `)`, and a wrapped call spans
# lines. The AST sees the call's real keyword list either way.
BANNED_CALLS: dict[str, tuple[str, str]] = {
    "utcnow": ("naive despite the name; deprecated in 3.12", "datetime.now(timezone.utc)"),
    "utcfromtimestamp": (
        "naive; deprecated alongside utcnow",
        "datetime.fromtimestamp(x, tz=timezone.utc)",
    ),
}

# `date +%Y-%m-%d` is the LOCAL day; it disagrees with the UTC day for
# `$(date +%z)` hours out of every 24, so a reader stamping local against a
# writer stamping UTC finds nothing for "today" during that window.
BANNED_SHELL = (
    (
        re.compile(r"date\s+\+%Y-%m-%d\b"),
        "local day, not UTC day",
        "date -u +%Y-%m-%d",
    ),
)

ALLOW_MARKER = "ts-allow"  # trailing comment opting one line out, with a reason


def _tracked(pattern: str) -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", pattern],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return [
        REPO_ROOT / line
        for line in out.stdout.splitlines()
        if line and not line.startswith(EXCLUDED_PREFIXES)
    ]


def _scan(paths: list[Path], rules) -> list[str]:
    violations = []
    for path in paths:
        rel = path.relative_to(REPO_ROOT)
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        for lineno, line in enumerate(lines, 1):
            if ALLOW_MARKER in line:
                continue
            for pattern, why, fix in rules:
                if pattern.search(line):
                    violations.append(
                        f"{rel}:{lineno} — {why}\n    use: {fix}\n    got: {line.strip()}"
                    )
    return violations


def _attr_name(node: ast.AST) -> str:
    return node.attr if isinstance(node, ast.Attribute) else getattr(node, "id", "")


def _scan_python_calls(path: Path, allowed_lines: set[int]) -> list[str]:
    rel = path.relative_to(REPO_ROOT)
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return []

    found = []
    for node in ast.walk(tree):
        # `datetime.UTC` landed in 3.11; pyproject declares requires-python
        # >=3.10, so this import is a collection-time ImportError there.
        if isinstance(node, ast.ImportFrom) and node.module == "datetime":
            if any(a.name == "UTC" for a in node.names) and node.lineno not in allowed_lines:
                found.append(
                    f"{rel}:{node.lineno} — `from datetime import UTC` needs Python 3.11+, "
                    "but requires-python is >=3.10\n    use: from datetime import timezone"
                )
            continue
        if not isinstance(node, ast.Call) or node.lineno in allowed_lines:
            continue
        name = _attr_name(node.func)

        if name in BANNED_CALLS:
            why, fix = BANNED_CALLS[name]
            found.append(f"{rel}:{node.lineno} — {name}(): {why}\n    use: {fix}")

        elif name == "fromtimestamp" and not any(kw.arg == "tz" for kw in node.keywords):
            found.append(
                f"{rel}:{node.lineno} — fromtimestamp() without tz=: renders a UTC "
                f"epoch in the server's local zone\n    use: fromtimestamp(x, tz=timezone.utc)"
            )

        elif name == "now" and not node.args and not node.keywords:
            found.append(
                f"{rel}:{node.lineno} — datetime.now() is naive local; wrong on any "
                f"machine outside UTC and twice a year under DST\n"
                f"    use: datetime.now(timezone.utc)  "
                f"(or mark the line '{ALLOW_MARKER}: <why local is correct>')"
            )

        elif name == "mktime" and node.args:
            inner = node.args[0]
            if isinstance(inner, ast.Call) and _attr_name(inner.func) == "strptime":
                found.append(
                    f"{rel}:{node.lineno} — mktime(strptime(...)) treats a parsed UTC "
                    f"struct as local — the documented Hub drift\n    use: calendar.timegm(...)"
                )
    return found


def test_no_banned_python_time_forms() -> None:
    violations = []
    for path in _tracked("*.py"):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        allowed = {n for n, line in enumerate(lines, 1) if ALLOW_MARKER in line}
        violations.extend(_scan_python_calls(path, allowed))
    assert not violations, (
        "Banned timestamp form(s) — see src/core/rules/timestamp-discipline.md:\n\n"
        + "\n\n".join(violations)
    )


def test_no_local_day_in_shell() -> None:
    paths = _tracked("*.sh")
    violations = _scan(paths, BANNED_SHELL)
    assert not violations, (
        "Local-day stamp in shell — see src/core/rules/timestamp-discipline.md:\n\n"
        + "\n\n".join(violations)
    )


def test_every_now_iso_producer_emits_the_same_shape() -> None:
    """The canonical producer and every inlined copy must agree byte-for-byte.

    src/core/hooks/_helpers/*.py deliberately do NOT import core.logging_os —
    cos_say_json.py documents avoiding that import on the hot hook path for
    latency — so the format is inlined in several emitters. That is permitted
    only while this test proves they are the same format.
    """
    import sys

    sys.path.insert(0, str(REPO_ROOT / "src" / "core"))
    from logging_os.clock import ISO_FORMAT, now_iso

    shape = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
    assert shape.match(now_iso()), f"canonical now_iso() drifted: {now_iso()!r}"

    copies = _scan_now_iso_bodies()
    assert copies, "found no _now_iso definitions — did the helper get renamed?"
    wrong = [f"{rel}: {body}" for rel, body in copies if ISO_FORMAT not in body]
    assert not wrong, (
        "these _now_iso copies emit a different shape than logging_os.clock "
        f"({ISO_FORMAT!r}), so the strict readers in logs.py / observability.py "
        "will silently drop their records:\n  " + "\n  ".join(wrong)
    )


def _scan_now_iso_bodies() -> list[tuple[str, str]]:
    found = []
    for path in _tracked("*.py"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for match in re.finditer(r"def _?now_iso\(\)[^\n]*:\n((?:\s+[^\n]*\n){1,4})", text):
            body = match.group(1).strip()
            # Conforming: delegates to the canonical producer, or names the
            # shared constant (clock.py itself, which DEFINES the format).
            if "return now_iso()" in body or "ISO_FORMAT" in body:
                continue
            found.append((str(path.relative_to(REPO_ROOT)), body))
    return found
