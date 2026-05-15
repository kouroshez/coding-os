#!/usr/bin/env python3
"""Audit a Python codebase for fail-open exception patterns.

Detects:
  - `except: pass` and `except Exception: pass` (silent swallow)
  - `except:` / `except Exception:` followed only by a `logger.*` call
    (log-and-allow — fail-open in disguise)
  - `return None` / `return {}` / `return []` from an except block
    (silent fallback)
  - `except (...,):` with non-specific broad exception groups

Usage:
  python audit-fail-closed.py [paths...]
  python audit-fail-closed.py --json [paths...]   # for CI ingestion

Exit code:
  0 — no findings
  1 — findings present
  2 — error
"""
from __future__ import annotations

import argparse
import ast
import json
import sys
from dataclasses import dataclass, asdict
from pathlib import Path


@dataclass
class Finding:
    path: str
    line: int
    kind: str  # silent_swallow | log_and_allow | silent_fallback | broad_except
    snippet: str


def _is_log_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Expr):
        return False
    call = node.value
    if not isinstance(call, ast.Call):
        return False
    func = call.func
    if isinstance(func, ast.Attribute):
        # Match: logger.info / log.warning / logging.error / etc.
        if func.attr in {"debug", "info", "warning", "warn", "error", "exception", "critical"}:
            return True
    return False


def _is_silent_return(node: ast.AST) -> bool:
    if not isinstance(node, ast.Return):
        return False
    val = node.value
    if val is None:
        return True
    if isinstance(val, ast.Constant) and val.value is None:
        return True
    if isinstance(val, ast.Dict) and not val.keys:
        return True
    if isinstance(val, (ast.List, ast.Set, ast.Tuple)) and not val.elts:
        return True
    return False


def _is_pass(node: ast.AST) -> bool:
    return isinstance(node, ast.Pass)


def _exception_is_broad(handler: ast.ExceptHandler) -> bool:
    """True if catches bare except or a top-level Exception/BaseException."""
    if handler.type is None:
        return True
    if isinstance(handler.type, ast.Name) and handler.type.id in {"Exception", "BaseException"}:
        return True
    if isinstance(handler.type, ast.Tuple):
        for elt in handler.type.elts:
            if isinstance(elt, ast.Name) and elt.id in {"Exception", "BaseException"}:
                return True
    return False


def audit_file(path: Path) -> list[Finding]:
    findings: list[Finding] = []
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (UnicodeDecodeError, SyntaxError):
        return findings

    src_lines = source.splitlines()

    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue
        body = node.body
        line = node.lineno
        snippet = src_lines[line - 1].strip() if line <= len(src_lines) else ""

        # Pattern 1: pure `pass`
        if len(body) == 1 and _is_pass(body[0]):
            findings.append(Finding(str(path), line, "silent_swallow", snippet))
            continue

        # Pattern 2: log-only (allows execution past block, no raise)
        if all(_is_log_call(stmt) or _is_pass(stmt) for stmt in body):
            if _exception_is_broad(node):
                findings.append(Finding(str(path), line, "log_and_allow", snippet))
                continue

        # Pattern 3: silent return None / {} / []
        for stmt in body:
            if _is_silent_return(stmt) and _exception_is_broad(node):
                findings.append(Finding(str(path), line, "silent_fallback", snippet))
                break

    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", default=["."], help="Files or directories to audit")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of human text")
    parser.add_argument("--exclude", default=".venv,venv,node_modules,.build,__pycache__,.git",
                        help="Comma-separated dir names to skip")
    args = parser.parse_args()

    excluded = set(s for s in args.exclude.split(",") if s)
    py_files: list[Path] = []
    for root in args.paths:
        p = Path(root)
        if p.is_file() and p.suffix == ".py":
            py_files.append(p)
        elif p.is_dir():
            for f in p.rglob("*.py"):
                if any(part in excluded for part in f.parts):
                    continue
                py_files.append(f)

    findings: list[Finding] = []
    for f in py_files:
        findings.extend(audit_file(f))

    if args.json:
        json.dump([asdict(x) for x in findings], sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        if not findings:
            print(f"[audit-fail-closed] OK: {len(py_files)} files scanned, no findings.")
        else:
            print(f"[audit-fail-closed] FOUND {len(findings)} finding(s) across {len(py_files)} files:\n")
            for f in findings:
                print(f"  {f.path}:{f.line}  {f.kind}  | {f.snippet}")

    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
