"""Flag common React/JSX correctness + performance smells.

PURPOSE:      Catch the re-render and key bugs that static types miss — one
              findings list per scan instead of reading every component.
INPUT:        one or more .jsx/.tsx files. [--json]
OUTPUT:       Findings (file:line) on stderr; "clean"/"N finding(s)" on stdout.
              Exit 0 clean, 1 if findings, 2 usage.
DEPENDENCIES: stdlib only (regex). Heuristic — pairs with eslint-plugin-react.
NOTES:        Pure scan_text() is unit-testable. Framework-specific rules live in
              the stack skill (nextjs-react / react-native). Spec:
              docs/playbooks/skill-authoring.md; craft: ../SKILL.md.
"""

from __future__ import annotations

import argparse
import json
import re
import sys

RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bkey=\{\s*(i|idx|index)\s*\}"),
     "array index as key — breaks reconciliation on reorder/insert; use a stable id"),
    (re.compile(r"\.map\((?:\([^)]*\)|\w+)\s*=>\s*<\w+(?![^>]*\bkey=)"),
     "list item rendered without a key prop"),
    (re.compile(r"\b\w+=\{\{"),
     "inline object literal prop — new reference each render → child re-renders; hoist/useMemo"),
    (re.compile(r"\b\w+=\{\s*\[[^\]]"),
     "inline array literal prop — new reference each render; hoist/useMemo"),
    (re.compile(r"dangerouslySetInnerHTML"),
     "dangerouslySetInnerHTML — XSS risk; sanitize or avoid"),
    (re.compile(r"useEffect\([^,]*\)\s*;"),
     "useEffect with no dependency array — runs every render"),
]


def scan_text(text: str, *, filename: str = "?") -> list[str]:
    findings: list[str] = []
    for n, line in enumerate(text.splitlines(), 1):
        stripped = line.lstrip()
        if stripped.startswith(("//", "*", "/*")):
            continue
        for pattern, msg in RULES:
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
            all_findings.extend(scan_text(open(path, encoding="utf-8").read(), filename=path))
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
