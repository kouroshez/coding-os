"""Scan PHP source for classic dangerous patterns (injection, RCE, weak hash).

PURPOSE:      Surface the high-risk PHP footguns in one pass so a reviewer reads
              a short findings list instead of every file.
INPUT:        one or more .php file paths. [--json]
OUTPUT:       Findings (file:line) on stderr; "clean"/"N finding(s)" on stdout.
              Exit 0 clean, 1 if findings, 2 usage.
DEPENDENCIES: stdlib only. Static regex scan — no PHP runtime needed.
NOTES:        Heuristic (regex, not a parser) — necessary not sufficient; pairs
              with PHPStan/Psalm. Pure scan_text() is unit-testable.
              Spec: docs/playbooks/skill-authoring.md; craft: ../SKILL.md.
"""

from __future__ import annotations

import argparse
import json
import re
import sys

REQUEST = r"\$_(GET|POST|REQUEST|COOKIE)"

# (compiled pattern, message) — each flags a high-risk construct.
RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\beval\s*\("), "eval() — arbitrary code execution"),
    (re.compile(rf"\bextract\s*\(\s*{REQUEST}"), "extract() on request data — variable injection"),
    (re.compile(rf"\b(system|exec|shell_exec|passthru|popen)\s*\([^)]*{REQUEST}"),
     "shell exec with request data — command injection"),
    (re.compile(rf"\bunserialize\s*\([^)]*{REQUEST}"), "unserialize() on request data — object-injection RCE"),
    (re.compile(rf"\b(include|require)(_once)?\s*[^;]*{REQUEST}"),
     "include/require with request path — file inclusion"),
    (re.compile(r"\bmysql_query\s*\("), "mysql_query() — removed/legacy; use PDO prepared statements"),
    (re.compile(rf"->query\s*\([^)]*{REQUEST}"), "request data concatenated into a query — SQL injection"),
    (re.compile(rf"\becho\s+[^;]*{REQUEST}[^;]*;"), "echo of raw request data — XSS; escape with htmlspecialchars"),
    (re.compile(r"\b(md5|sha1)\s*\(\s*\$(pass|pwd|password)", re.IGNORECASE),
     "md5/sha1 for a password — use password_hash()"),
]

STRICT_TYPES = re.compile(r"declare\s*\(\s*strict_types\s*=\s*1\s*\)")


def scan_text(text: str, *, filename: str = "?") -> list[str]:
    findings: list[str] = []
    lines = text.splitlines()
    for n, line in enumerate(lines, 1):
        if line.lstrip().startswith(("//", "*", "#")):
            continue
        for pattern, msg in RULES:
            if pattern.search(line):
                findings.append(f"{filename}:{n}: {msg}")
    if "<?php" in text and not STRICT_TYPES.search(text):
        findings.append(f"{filename}: no declare(strict_types=1) — types coerce silently")
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
