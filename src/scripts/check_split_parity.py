#!/usr/bin/env python3
"""Prove a module split moved code without editing it.

A split is a code MOVE. Every function that existed before must still exist,
with a byte-identical body, somewhere in the post-split package. A suite can
stay green while a moved body lost a line — the 2026-08-10 `_normalized_hook_map`
regression dropped `return normalized`, turned every comparison into
`None != None`, and made `cos doctor` report a stale adapter as healthy.

    uv run python src/scripts/check_split_parity.py <git-ref> <old-path> <new-path>...

A <new-path> may be a directory, which is the safer form: pass the package the
split landed in and every sibling is scanned. Naming files by hand produces
false VANISHED reports for functions that simply went somewhere unlisted.

Reports functions that vanished and functions whose body changed. A deliberate
edit shows up here too — that is the point: it must be a separate commit from
the move. Spec: docs/engineering/ci-gates.md.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path


def _functions(source: str, origin: str) -> dict[str, list[tuple[str, str]]]:
    found: dict[str, list[tuple[str, str]]] = {}
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            found.setdefault(node.name, []).append((ast.unparse(node), origin))
    return found


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(__doc__)
        return 2
    ref, old_path, *new_paths = argv

    before_text = subprocess.run(
        ["git", "show", f"{ref}:{old_path}"], capture_output=True, text=True, check=True
    ).stdout
    before = _functions(before_text, old_path)

    after: dict[str, list[tuple[str, str]]] = {}
    scanned: list[Path] = []
    for raw in new_paths:
        target = Path(raw)
        scanned.extend(sorted(target.rglob("*.py")) if target.is_dir() else [target])
    for path in scanned:
        for name, defs in _functions(path.read_text(encoding="utf-8"), str(path)).items():
            after.setdefault(name, []).extend(defs)

    missing = sorted(name for name in before if name not in after)
    # A name can be defined in several scanned modules; the move is intact as
    # long as ONE of them still carries the original body.
    changed = sorted(
        f"{name}  (candidates: {', '.join(origin for _, origin in after[name])})"
        for name, defs in before.items()
        if name in after and not any(body == defs[0][0] for body, _ in after[name])
    )

    if missing:
        print(f"VANISHED — {len(missing)} function(s) present before the split, absent after:")
        for name in missing:
            print(f"  {name}")
    if changed:
        print(f"EDITED — {len(changed)} moved function(s) whose body is not byte-identical:")
        for entry in changed:
            print(f"  {entry}")
    if missing or changed:
        print("\nA split is a move. Land behaviour changes as their own commit.")
        return 1

    print(f"OK — all {len(before)} function(s) moved unchanged across {len(scanned)} module(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
