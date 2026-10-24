"""Lint a GitHub Actions workflow for supply-chain + reliability footguns.

PURPOSE:      Flag unpinned actions, leaked secrets, and missing timeouts so a
              pipeline is reproducible and not a supply-chain hole.
INPUT:        one or more workflow .yml/.yaml paths. [--json]
OUTPUT:       Findings (file:line) on stderr; "clean"/"N finding(s)" on stdout.
              Exit 0 clean, 1 if findings, 2 usage.
DEPENDENCIES: stdlib only (regex — no YAML parser needed, portable).
NOTES:        Heuristic. Pure scan_text() is unit-testable. Spec:
              docs/playbooks/skill-authoring.md; craft: ../SKILL.md.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# uses: owner/repo@<ref> — flag moving refs and missing refs.
USES_MOVING = re.compile(r"uses:\s*[\w.-]+/[\w.-]+@(main|master|latest)\b")
USES_NOREF = re.compile(r"uses:\s*[\w.-]+/[\w.-]+\s*$")
# secret echoed into a run step (printed = exposed in logs)
SECRET_ECHO = re.compile(r"(echo|print|cat)[^\n]*\$\{\{\s*secrets\.")
RUN_CURL_BASH = re.compile(r"curl[^\n]*\|\s*(sudo\s+)?(bash|sh)\b")


def scan_text(text: str, *, filename: str = "?") -> list[str]:
    findings: list[str] = []
    has_timeout = "timeout-minutes" in text
    has_job = re.search(r"^\s*jobs:\s*$", text, re.MULTILINE) is not None
    for n, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith("#"):
            continue
        if USES_MOVING.search(line):
            findings.append(
                f"{filename}:{n}: action pinned to a moving ref (@main/master/latest) — pin a tag/SHA"
            )
        elif USES_NOREF.search(line):
            findings.append(f"{filename}:{n}: action with no @version — pin a tag/SHA")
        if SECRET_ECHO.search(line):
            findings.append(f"{filename}:{n}: secret echoed into a step — leaks in logs")
        if RUN_CURL_BASH.search(line):
            findings.append(
                f"{filename}:{n}: curl | bash from an unpinned source — supply-chain risk"
            )
    if has_job and not has_timeout:
        findings.append(
            f"{filename}: no timeout-minutes on any job — a hung job runs until the platform cap"
        )
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
