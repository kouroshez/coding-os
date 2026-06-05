"""Scan WordPress plugin/theme PHP for the WP-specific security footguns.

PURPOSE:      Flag missing nonce checks, raw $wpdb queries, unescaped output,
              and __return_true REST permissions — one findings list per scan.
INPUT:        one or more .php file paths. [--json]
OUTPUT:       Findings (file:line) on stderr; "clean"/"N finding(s)" on stdout.
              Exit 0 clean, 1 if findings, 2 usage.
DEPENDENCIES: stdlib only. Static regex scan; pairs with PHPCS WordPress rules.
NOTES:        Heuristic — necessary not sufficient. Pure scan_text()/scan_file()
              are unit-testable. The generic-PHP footguns live in the php skill's
              scanner; this one is WordPress-specific.
              Spec: docs/playbooks/skill-authoring.md; craft: ../SKILL.md.
"""

from __future__ import annotations

import argparse
import json
import re
import sys

REQUEST = r"\$_(GET|POST|REQUEST)"

LINE_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(rf"\$wpdb->(query|get_results|get_var|get_row)\s*\([^)]*{REQUEST}"),
     "$wpdb call with raw request data — use $wpdb->prepare() with %d/%s"),
    (re.compile(rf"\becho\s+[^;]*{REQUEST}"), "echo of raw request data — escape (esc_html/esc_attr)"),
    (re.compile(r"'permission_callback'\s*=>\s*'__return_true'"),
     "REST permission_callback __return_true — add a capability check"),
    (re.compile(r"\bwp_table\b|\bwp_posts\b|\bwp_users\b"),
     "hardcoded wp_ table name — use $wpdb->posts / $wpdb->prefix"),
]

# File-level: a handler that touches request data but never verifies a nonce
# or a capability. Heuristic at file scope.
NONCE = re.compile(r"wp_verify_nonce|check_admin_referer|check_ajax_referer")
CAP = re.compile(r"current_user_can|user_can")
TOUCHES_REQUEST = re.compile(REQUEST)


def scan_text(text: str, *, filename: str = "?") -> list[str]:
    findings: list[str] = []
    for n, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith(("//", "*", "#")):
            continue
        for pattern, msg in LINE_RULES:
            if pattern.search(line):
                findings.append(f"{filename}:{n}: {msg}")
    if TOUCHES_REQUEST.search(text):
        if not NONCE.search(text):
            findings.append(f"{filename}: touches request data but no nonce verification (CSRF)")
        if not CAP.search(text):
            findings.append(f"{filename}: touches request data but no capability check (privilege)")
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
