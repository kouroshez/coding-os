"""Flag cos_* MCP tools that violate the envelope contract (Rule 13).

PURPOSE:      Catch a @mcp.tool that lacks @safe_tool or doesn't return ok/fail
              before it ships — the envelope is what every caller + test relies on.
INPUT:        one or more tools/*.py paths. [--json]
OUTPUT:       Findings (file:line) on stderr; "clean"/"N finding(s)" on stdout.
              Exit 0 clean, 1 if findings, 2 usage.
DEPENDENCIES: stdlib only (ast — accurate, not regex).
NOTES:        Pure scan_source() is unit-testable. Spec:
              docs/engineering/mcp-error-envelope.md; craft: ../SKILL.md.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path


def _decorator_names(node: ast.FunctionDef) -> set[str]:
    names: set[str] = set()
    for dec in node.decorator_list:
        target = dec.func if isinstance(dec, ast.Call) else dec
        if isinstance(target, ast.Name):
            names.add(target.id)
        elif isinstance(target, ast.Attribute):
            names.add(target.attr)
    return names


def _returns_envelope(node: ast.FunctionDef) -> bool:
    for sub in ast.walk(node):
        if isinstance(sub, ast.Return) and isinstance(sub.value, ast.Call):
            fn = sub.value.func
            if isinstance(fn, ast.Name) and fn.id in {"ok", "fail"}:
                return True
    return False


def scan_source(text: str, *, filename: str = "?") -> list[str]:
    findings: list[str] = []
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        decs = _decorator_names(node)
        if "tool" not in decs:           # only @mcp.tool() functions
            continue
        if "safe_tool" not in decs:
            findings.append(f"{filename}:{node.lineno}: {node.name} is @mcp.tool but not @safe_tool (Rule 13)")
        if not node.name.startswith("cos_"):
            findings.append(f"{filename}:{node.lineno}: {node.name} missing cos_ prefix (Rule 2)")
        if not _returns_envelope(node):
            findings.append(f"{filename}:{node.lineno}: {node.name} never returns ok()/fail() (Rule 13)")
    return findings


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("files", nargs="+")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)

    all_findings: list[str] = []
    for path in args.files:
        try:
            all_findings.extend(scan_source(Path(path).read_text(encoding="utf-8"), filename=path))
        except FileNotFoundError:
            print(f"error: {path} not found", file=sys.stderr)
            return 2
        except SyntaxError as exc:
            print(f"error: {path}: {exc}", file=sys.stderr)
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
