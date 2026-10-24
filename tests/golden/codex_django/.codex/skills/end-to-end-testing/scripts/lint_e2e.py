"""Lint Playwright spec files for the common flakiness anti-patterns.

PURPOSE:      Flag hard sleeps, brittle selectors, and assertion-free tests so a
              suite stays reliable instead of teaching the team to ignore red.
INPUT:        one or more Playwright spec paths (*.spec.ts / *.ts). [--json]
OUTPUT:       Findings (file:line) on stderr; "clean"/"N finding(s)" on stdout.
              Exit 0 clean, 1 if findings, 2 usage.
DEPENDENCIES: stdlib only. Static regex scan.
NOTES:        Heuristic — necessary not sufficient. Pure scan_text() is
              unit-testable. Spec: docs/playbooks/skill-authoring.md; craft: ../SKILL.md.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

LINE_RULES: list[tuple[re.Pattern, str]] = [
    (
        re.compile(r"\bwaitForTimeout\s*\("),
        "waitForTimeout (hard sleep) — use an auto-waiting expect",
    ),
    (
        re.compile(r"\b(setTimeout|sleep)\s*\("),
        "manual sleep — use an auto-waiting locator/assertion",
    ),
    (
        re.compile(r"page\.(click|fill|type)\s*\(\s*['\"](\.|#)[\w-]*\d"),
        "CSS selector with a generated/positional class — use getByRole/getByTestId",
    ),
    (
        re.compile(r"locator\(\s*['\"][^'\"]*:nth-child"),
        "nth-child selector — brittle; use a semantic locator",
    ),
    (re.compile(r"\bpage\.\$x?\("), "page.$ / page.$x (deprecated, no auto-wait) — use locators"),
    (
        re.compile(r"\bxpath=|\bpage\.\$x\("),
        "XPath selector — brittle; use a role/label/text locator",
    ),
]

TEST_DECL = re.compile(r"\b(test|it)\s*\(\s*['\"]")
HAS_ASSERT = re.compile(r"\bexpect\s*\(")


def scan_text(text: str, *, filename: str = "?") -> list[str]:
    findings: list[str] = []
    for n, line in enumerate(text.splitlines(), 1):
        stripped = line.lstrip()
        if stripped.startswith(("//", "*", "/*")):
            continue
        for pattern, msg in LINE_RULES:
            if pattern.search(line):
                findings.append(f"{filename}:{n}: {msg}")
    # A spec file with test blocks but no expect() asserts nothing.
    if TEST_DECL.search(text) and not HAS_ASSERT.search(text):
        findings.append(f"{filename}: test(s) with no expect() — the test asserts nothing")
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
