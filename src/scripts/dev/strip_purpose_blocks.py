"""Strip legacy PURPOSE/INPUT/OUTPUT/DEPENDENCIES/NOTES docstring blocks.

Per AGENTS.md Rule 12 (rewritten 2026-05-05).
Usage: python scripts/dev/strip_purpose_blocks.py [--apply]
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TARGET_DIRS = ["core", "cli", "adapters", "scripts", "tests"]
EXCLUDE_DIRS = {"__pycache__", ".coding-os", "node_modules", ".venv", "dist", "build"}
SECTION_KEYWORDS = ("PURPOSE:", "INPUT:", "OUTPUT:", "DEPENDENCIES:", "NOTES:")


def _iter_py_files() -> list[Path]:
    files: list[Path] = []
    for d in TARGET_DIRS:
        for p in (ROOT / d).rglob("*.py"):
            if any(part in EXCLUDE_DIRS for part in p.parts):
                continue
            files.append(p)
    return files


def _strip_purpose(text: str) -> str | None:
    if "PURPOSE:" not in text:
        return None
    lines = text.splitlines()
    keep: list[str] = []
    in_section = False
    section_indent: int | None = None

    for ln in lines:
        stripped = ln.lstrip()
        starts_section = any(stripped.startswith(kw) for kw in SECTION_KEYWORDS)

        if starts_section:
            in_section = True
            section_indent = len(ln) - len(stripped)
            continue

        if in_section:
            if not stripped:
                continue
            cur_indent = len(ln) - len(stripped)
            if section_indent is not None and cur_indent > section_indent:
                continue
            in_section = False
            section_indent = None

        keep.append(ln)

    while keep and not keep[0].strip():
        keep.pop(0)
    while keep and not keep[-1].strip():
        keep.pop()

    return "\n".join(keep)


def _process_file(path: Path) -> tuple[int, int, str]:
    src = path.read_text(encoding="utf-8")
    if "PURPOSE:" not in src:
        return (0, 0, src)
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return (0, 0, src)

    src_lines = src.splitlines(keepends=True)
    edits: list[tuple[int, int, str]] = []
    modified = 0
    removed = 0

    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        body = getattr(node, "body", None)
        if not body:
            continue
        first = body[0]
        if not isinstance(first, ast.Expr):
            continue
        if not isinstance(first.value, ast.Constant) or not isinstance(first.value.value, str):
            continue

        new_text = _strip_purpose(first.value.value)
        if new_text is None:
            continue

        start_line = first.lineno - 1
        end_line = first.end_lineno

        if not new_text.strip():
            siblings = [s for s in body if s is not first]
            if not siblings and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                indent = " " * first.col_offset
                edits.append((start_line, end_line, f"{indent}pass\n"))
            else:
                edits.append((start_line, end_line, ""))
            removed += 1
        else:
            indent = " " * first.col_offset
            if "\n" in new_text:
                rebuilt = f'{indent}"""{new_text}\n{indent}"""\n'
            else:
                rebuilt = f'{indent}"""{new_text}"""\n'
            edits.append((start_line, end_line, rebuilt))
            modified += 1

    if not edits:
        return (0, 0, src)

    edits.sort(key=lambda e: e[0], reverse=True)
    for start, end, replacement in edits:
        src_lines[start:end] = [replacement] if replacement else []

    return (modified, removed, "".join(src_lines))


def main(apply: bool) -> int:
    total_files = 0
    total_modified = 0
    total_removed = 0

    for path in _iter_py_files():
        modified, removed, new_src = _process_file(path)
        if modified == 0 and removed == 0:
            continue
        total_files += 1
        total_modified += modified
        total_removed += removed
        if apply:
            path.write_text(new_src, encoding="utf-8")
            print(f"  rewrote {path.relative_to(ROOT)}: {modified} stripped, {removed} removed")

    mode = "APPLIED" if apply else "DRY RUN"
    print(f"\n{mode}")
    print(f"  files affected:        {total_files}")
    print(f"  PURPOSE blocks stripped (summary kept):     {total_modified}")
    print(f"  docstrings removed entirely (PURPOSE-only): {total_removed}")
    if not apply and total_files:
        print("\n  rerun with --apply to write changes")
    return 0


if __name__ == "__main__":
    sys.exit(main(apply="--apply" in sys.argv))
