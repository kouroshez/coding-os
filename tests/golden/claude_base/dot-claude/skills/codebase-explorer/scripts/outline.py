"""Print a fast structural outline of a source file (classes, functions, exports).

PURPOSE:      Orient in an unfamiliar file in one call — the shape (what's
              defined, where) without reading every line or needing the graph.
INPUT:        one or more source paths (.py / .ts / .tsx / .js / .jsx). [--json]
OUTPUT:       An indented outline per file on stdout. Exit 0; 2 on usage.
DEPENDENCIES: stdlib only (ast for Python, regex for TS/JS) — works in any repo.
NOTES:        Python uses the real AST (accurate); TS/JS uses a regex heuristic
              (top-level decls). Pure outline_python()/outline_ts() are
              unit-testable. Complements graph-explorer (this is zero-dependency,
              single-file, no MCP). Spec: docs/playbooks/skill-authoring.md.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path


def outline_python(text: str) -> list[dict]:
    tree = ast.parse(text)
    items: list[dict] = []

    def visit(node: ast.AST, depth: int) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                items.append(
                    {"kind": "func", "name": child.name, "line": child.lineno, "depth": depth}
                )
                visit(child, depth + 1)
            elif isinstance(child, ast.ClassDef):
                items.append(
                    {"kind": "class", "name": child.name, "line": child.lineno, "depth": depth}
                )
                visit(child, depth + 1)

    visit(tree, 0)
    return items


_TS_DECL = re.compile(
    r"^(?P<indent>\s*)(export\s+)?(default\s+)?"
    r"(?P<kind>class|interface|type|enum|function|const|let)\s+(?P<name>\w+)",
)


def outline_ts(text: str) -> list[dict]:
    items: list[dict] = []
    for n, line in enumerate(text.splitlines(), 1):
        m = _TS_DECL.match(line)
        if m:
            depth = len(m.group("indent")) // 2
            items.append(
                {"kind": m.group("kind"), "name": m.group("name"), "line": n, "depth": depth}
            )
    return items


def outline_file(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".py":
        return outline_python(text)
    return outline_ts(text)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("files", nargs="+")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)

    result: dict[str, list[dict]] = {}
    for p in args.files:
        path = Path(p)
        try:
            result[p] = outline_file(path)
        except FileNotFoundError:
            print(f"error: {p} not found", file=sys.stderr)
            return 2
        except SyntaxError as exc:
            print(f"error: {p}: {exc}", file=sys.stderr)
            return 2

    if args.as_json:
        print(json.dumps(result, indent=2))
    else:
        for p, items in result.items():
            print(p)
            for it in items:
                print(f"  {'  ' * it['depth']}{it['kind']} {it['name']}  :{it['line']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
