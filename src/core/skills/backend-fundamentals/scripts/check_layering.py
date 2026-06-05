"""Flag web-framework / ORM leakage into domain/service-layer files.

PURPOSE:      Keep business logic framework-free (hexagonal): a service or domain
              file that imports Flask/FastAPI/Express/an ORM has coupled the
              core to delivery/infra, making it hard to test and swap.
INPUT:        one or more source paths the caller considers domain/service code.
              [--json]
OUTPUT:       Findings (file:line) on stderr; "clean"/"N finding(s)" on stdout.
              Exit 0 clean, 1 if findings, 2 usage.
DEPENDENCIES: stdlib only (regex). Heuristic — you choose which files to pass.
NOTES:        Pure scan_text() is unit-testable. The hexagonal principle is
              owned by the hexagonal-architecture skill. Spec:
              docs/playbooks/skill-authoring.md; craft: ../SKILL.md.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Imports that signal delivery (web) or infra (ORM/driver) inside core code.
RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"^\s*(from|import)\s+(flask|fastapi|django|starlette)\b"),
     "web framework imported in domain/service code — keep the core framework-free"),
    (re.compile(r"require\(['\"]express['\"]\)|from\s+['\"]express['\"]"),
     "Express imported in domain/service code — move HTTP concerns to the delivery layer"),
    (re.compile(r"^\s*(from|import)\s+(sqlalchemy|django\.db|psycopg2?|pymongo)\b"),
     "ORM/driver imported in domain/service code — depend on a repository port, not the driver"),
    (re.compile(r"\b(request|Request|Response|res\.json|req\.body)\b.*=|def\s+\w+\([^)]*\brequest\b"),
     "HTTP request/response object in domain/service code — pass plain data in, return plain data out"),
]


def scan_text(text: str, *, filename: str = "?") -> list[str]:
    findings: list[str] = []
    for n, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith(("#", "//", "*")):
            continue
        for pattern, msg in RULES:
            if pattern.search(line):
                findings.append(f"{filename}:{n}: {msg}")
                break
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
