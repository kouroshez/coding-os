"""Flag React Native list/render performance smells.

PURPOSE:      Catch the RN-specific perf footguns (inline renderItem, missing
              keyExtractor, ScrollView for long lists) that tank scroll FPS.
INPUT:        one or more .tsx/.jsx files. [--json]
OUTPUT:       Findings (file:line) on stderr; "clean"/"N finding(s)" on stdout.
              Exit 0 clean, 1 if findings, 2 usage.
DEPENDENCIES: stdlib only (regex). Heuristic — pairs with eslint + Flipper.
NOTES:        Pure scan_text() is unit-testable. Spec:
              docs/playbooks/skill-authoring.md; craft: ../SKILL.md.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

LINE_RULES: list[tuple[re.Pattern, str]] = [
    (
        re.compile(r"renderItem=\{\s*\([^)]*\)\s*=>"),
        "inline renderItem arrow — new function each render; hoist + useCallback",
    ),
    (
        re.compile(r"<(FlatList|FlashList|SectionList)\b(?![^>]*keyExtractor)", re.DOTALL),
        "list without keyExtractor — falls back to index keys; provide a stable id",
    ),
    (
        re.compile(r"style=\{\{"),
        "inline style object — new reference each render; StyleSheet.create or hoist",
    ),
    (
        re.compile(r"<ScrollView\b[^>]*>\s*\{[^}]*\.map\("),
        "ScrollView rendering a mapped list — renders all items; use FlatList/FlashList",
    ),
]


def scan_text(text: str, *, filename: str = "?") -> list[str]:
    findings: list[str] = []
    for n, line in enumerate(text.splitlines(), 1):
        stripped = line.lstrip()
        if stripped.startswith(("//", "*", "/*")):
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
