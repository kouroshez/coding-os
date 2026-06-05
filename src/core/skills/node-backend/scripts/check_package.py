"""Audit a package.json for backend production-readiness signals.

PURPOSE:      Flag a package.json that will bite in production — no engine pin,
              no lockfile alongside, install-not-ci, missing start script.
INPUT:        package.json path (default package.json) or --file. [--json]
OUTPUT:       Findings on stderr; "clean"/"N finding(s)" on stdout. Exit 0
              clean, 1 findings, 2 usage/parse error.
DEPENDENCIES: stdlib only.
NOTES:        Pure audit() is unit-testable. Lockfile check is filesystem-aware
              only in main(); audit() takes a `has_lockfile` flag so it stays
              pure. Spec: docs/playbooks/skill-authoring.md; craft: ../SKILL.md.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

LOCKFILES = ("package-lock.json", "pnpm-lock.yaml", "yarn.lock", "bun.lockb")


def audit(pkg: dict, *, has_lockfile: bool) -> list[str]:
    findings: list[str] = []
    engines = pkg.get("engines", {})
    if not isinstance(engines, dict) or "node" not in engines:
        findings.append("no engines.node — pin the Node version (LTS) for reproducible runtime")
    if not has_lockfile:
        findings.append("no lockfile alongside (package-lock/pnpm-lock/yarn.lock) — "
                        "builds are not reproducible")
    scripts = pkg.get("scripts", {})
    if isinstance(scripts, dict):
        for name, body in scripts.items():
            if isinstance(body, str) and "npm install" in body:
                findings.append(f"script '{name}' runs 'npm install' (mutates lockfile) — use 'npm ci'")
        if "start" not in scripts:
            findings.append("no 'start' script — define the production entrypoint")
    return findings


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("path", nargs="?", default="package.json")
    parser.add_argument("--file", default=None)
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)

    target = Path(args.file or args.path)
    try:
        pkg = json.loads(target.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"error: {target} not found", file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print(f"error: {target}: {exc}", file=sys.stderr)
        return 2
    if not isinstance(pkg, dict):
        print(f"error: {target}: root must be an object", file=sys.stderr)
        return 2

    has_lockfile = any((target.parent / lf).exists() for lf in LOCKFILES)
    findings = audit(pkg, has_lockfile=has_lockfile)

    for f in findings:
        print(f"  ✗ {f}", file=sys.stderr)
    if args.as_json:
        print(json.dumps({"findings": findings, "count": len(findings)}))
    else:
        print("clean" if not findings else f"{len(findings)} finding(s)")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
