"""Lint source for logging-hygiene problems (print, eager format, PII, no level).

PURPOSE:      Catch the logging mistakes that make production unobservable or
              leak data — one findings list instead of reading every log call.
INPUT:        one or more source paths (.py/.ts/.js/.go). [--json]
OUTPUT:       Findings (file:line) on stderr; "clean"/"N finding(s)" on stdout.
              Exit 0 clean, 1 if findings, 2 usage.
DEPENDENCIES: stdlib only. Static regex scan; heuristic.
NOTES:        Pure scan_text() is unit-testable. PII/secret policy is owned by
              security-web + the memory rule; this flags the log-call shape.
              Spec: docs/playbooks/skill-authoring.md; craft: ../SKILL.md.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PII = r"(password|passwd|secret|token|api[_-]?key|ssn|credit[_-]?card|email|authorization)"

LINE_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"^\s*print\s*\(", re.IGNORECASE), "print() — use a structured logger, not stdout"),
    (
        re.compile(r"console\.(log|error|warn)\s*\("),
        "console.log — use a structured logger with levels + context",
    ),
    (
        re.compile(rf"log(ger)?\.\w+\([^)]*{PII}", re.IGNORECASE),
        "PII/secret-shaped value in a log call — redact or use an id",
    ),
    (
        re.compile(r"log(ger)?\.\w+\(\s*f['\"]"),
        "f-string in a log call — eager-formats even when the level is disabled; pass args separately",
    ),
]


def scan_text(text: str, *, filename: str = "?") -> list[str]:
    findings: list[str] = []
    for n, line in enumerate(text.splitlines(), 1):
        stripped = line.lstrip()
        if stripped.startswith(("#", "//", "*", "/*")):
            continue
        for pattern, msg in LINE_RULES:
            if pattern.search(line):
                findings.append(f"{filename}:{n}: {msg}")
    return findings


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("files", nargs="+")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)

    all_findings: list[str] = []
    for path in args.files:
        try:
            all_findings.extend(scan_text(Path(path).read_text(encoding="utf-8"), filename=path))
        except FileNotFoundError:
            print(f"error: {path} not found", file=sys.stderr)
            return 2

    for f in all_findings:
        print(f"  ✗ {f}", file=sys.stderr)
    if args.as_json:
        print(json.dumps({"findings": all_findings, "count": len(all_findings)}))
    else:
        print("clean" if not all_findings else f"{len(all_findings)} finding(s)")
    return 1 if all_findings else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
