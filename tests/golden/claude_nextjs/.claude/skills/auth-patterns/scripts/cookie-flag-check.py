#!/usr/bin/env python3
"""Audit Set-Cookie usage for missing security flags.

Scans Python (Django + FastAPI + raw Werkzeug/Flask), TypeScript (Express,
Next.js Route Handlers, Hono), and Go (Fiber, stdlib net/http) source
files for cookie-setting calls without Secure/HttpOnly/SameSite.

Usage:
  python cookie-flag-check.py [paths...]
  python cookie-flag-check.py --json [paths...]

Exit code 1 if any finding.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

# Lightweight regex audit — not a full parser. Trade-off: occasional false
# positive worth the simplicity. Run with --json in CI; review findings.

# Python: response.set_cookie(...), Cookie('...'), HttpResponse(...).set_cookie
PY_COOKIE_PATTERNS = [
    re.compile(r"\.set_cookie\s*\("),
    re.compile(r"response\.cookies\s*\["),
    re.compile(r"morsel\s*=\s*Morsel"),
]
PY_REQUIRED_FLAGS = ["httponly", "secure", "samesite"]

# TypeScript / JS: res.cookie(...), res.setHeader('Set-Cookie', ...), cookies().set(...)
TS_COOKIE_PATTERNS = [
    re.compile(r"\bres\.cookie\s*\("),
    re.compile(r"\bsetHeader\s*\(\s*['\"]Set-Cookie['\"]"),
    re.compile(r"\bcookies\(\)\.set\s*\("),
]
TS_REQUIRED_FLAGS = ["httpOnly", "secure", "sameSite"]

# Go: c.Cookie(&fiber.Cookie{...}), http.SetCookie(...)
GO_COOKIE_PATTERNS = [
    re.compile(r"\bc\.Cookie\s*\(&fiber\.Cookie"),
    re.compile(r"\bhttp\.SetCookie\s*\("),
]
GO_REQUIRED_FLAGS = ["HttpOnly", "Secure", "SameSite"]


@dataclass
class Finding:
    path: str
    line: int
    missing: list[str]
    snippet: str


def _audit_block(text: str, start: int, required: list[str], window: int = 12) -> list[str]:
    """From `start`, scan up to `window` lines forward; return missing flags."""
    lines = text.splitlines()
    end = min(len(lines), start + window)
    block = "\n".join(lines[start:end]).lower()
    missing = [f for f in required if f.lower() not in block]
    return missing


def audit_file(path: Path) -> list[Finding]:
    findings: list[Finding] = []
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return findings

    ext = path.suffix.lower()
    if ext in {".py"}:
        patterns, required = PY_COOKIE_PATTERNS, PY_REQUIRED_FLAGS
    elif ext in {".ts", ".tsx", ".js", ".jsx", ".mts", ".mjs"}:
        patterns, required = TS_COOKIE_PATTERNS, TS_REQUIRED_FLAGS
    elif ext in {".go"}:
        patterns, required = GO_COOKIE_PATTERNS, GO_REQUIRED_FLAGS
    else:
        return findings

    lines = text.splitlines()
    for i, line in enumerate(lines):
        for pat in patterns:
            if pat.search(line):
                missing = _audit_block(text, i, required)
                if missing:
                    findings.append(
                        Finding(
                            path=str(path),
                            line=i + 1,
                            missing=missing,
                            snippet=line.strip()[:120],
                        )
                    )
                break  # one finding per line max
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", default=["."])
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--exclude", default=".venv,venv,node_modules,.build,dist,__pycache__,.git,vendor"
    )
    args = parser.parse_args()

    excluded = {s for s in args.exclude.split(",") if s}
    target_files: list[Path] = []
    for root in args.paths:
        p = Path(root)
        if p.is_file():
            target_files.append(p)
        elif p.is_dir():
            for f in p.rglob("*"):
                if not f.is_file():
                    continue
                if any(part in excluded for part in f.parts):
                    continue
                if f.suffix.lower() in {".py", ".ts", ".tsx", ".js", ".jsx", ".mts", ".mjs", ".go"}:
                    target_files.append(f)

    findings: list[Finding] = []
    for f in target_files:
        findings.extend(audit_file(f))

    if args.json:
        json.dump([asdict(x) for x in findings], sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        if not findings:
            print(f"[cookie-flag-check] OK: {len(target_files)} files scanned, no findings.")
        else:
            print(f"[cookie-flag-check] FOUND {len(findings)} finding(s):\n")
            for f in findings:
                print(f"  {f.path}:{f.line}  missing={','.join(f.missing)}  | {f.snippet}")

    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
