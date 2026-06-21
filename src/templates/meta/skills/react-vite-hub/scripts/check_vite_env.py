"""Flag Vite client-env footguns (process.env, non-VITE_ vars in client code).

PURPOSE:      Catch env access that silently breaks in a Vite build — Vite only
              exposes import.meta.env.VITE_* to the client; process.env and
              non-prefixed vars are undefined at runtime.
INPUT:        one or more UI source paths (.ts/.tsx/.js/.jsx). [--json]
OUTPUT:       Findings (file:line) on stderr; "clean"/"N finding(s)" on stdout.
              Exit 0 clean, 1 if findings, 2 usage.
DEPENDENCIES: stdlib only (regex).
NOTES:        Pure scan_text() is unit-testable. Spec: docs/engineering/hub-architecture.md;
              craft: ../SKILL.md.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PROCESS_ENV = re.compile(r"\bprocess\.env\b")
# import.meta.env.X where X is NOT VITE_-prefixed (and not the built-ins).
BUILTINS = {"MODE", "BASE_URL", "PROD", "DEV", "SSR"}
META_ENV = re.compile(r"import\.meta\.env\.(\w+)")


def scan_text(text: str, *, filename: str = "?") -> list[str]:
    findings: list[str] = []
    for n, line in enumerate(text.splitlines(), 1):
        stripped = line.lstrip()
        if stripped.startswith(("//", "*", "/*")):
            continue
        if PROCESS_ENV.search(line):
            findings.append(
                f"{filename}:{n}: process.env in client code — undefined in a Vite build; "
                "use import.meta.env.VITE_*"
            )
        for m in META_ENV.finditer(line):
            var = m.group(1)
            if var not in BUILTINS and not var.startswith("VITE_"):
                findings.append(
                    f"{filename}:{n}: import.meta.env.{var} not VITE_-prefixed — "
                    "Vite won't expose it to the client"
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
