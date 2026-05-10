"""Insert `> Nav:` line after the opening block on docs missing it."""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
DOCS = REPO / "docs"
SKIP_DIRS = {"governance", "code-os-core-docs"}

_FRONTMATTER = re.compile(r"^<!--\s*domain:.*-->\s*$")
_H1 = re.compile(r"^#\s+")
_NAV = re.compile(r"^>\s*Nav:")
_OPENING_LINE = re.compile(r"^(Purpose:|Read when:|Skip when:|Read next:|>\s*[PRSN]:)")


def _nav_for(rel: Path) -> str:
    parts = rel.parts
    if rel.name == "00-index.md" and len(parts) == 1:
        # Root index.
        return "> Nav: [Repo](../README.md)"
    if rel.name == "00-index.md":
        # Sub-directory index.
        return "> Nav: [Docs Index](../00-index.md)"
    if len(parts) > 1:
        # File inside a sub-directory.
        return "> Nav: [Section Index](./00-index.md) | [Docs Index](../00-index.md)"
    # File at docs/ root with no sibling section index.
    return "> Nav: [Docs Index](./00-index.md)"


def _insert_nav(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines:
        return False

    # Skip files without frontmatter or H1 — they're not part of the spec.
    has_frontmatter = any(_FRONTMATTER.match(ln) for ln in lines[:3])
    h1_idx = next((i for i, ln in enumerate(lines[:5]) if _H1.match(ln)), None)
    if not has_frontmatter or h1_idx is None:
        return False

    if any(_NAV.match(ln) for ln in lines[: h1_idx + 20]):
        return False

    # Find insertion point: end of opening block, else right after H1 + blank.
    insert_at = h1_idx + 1
    cursor = h1_idx + 1
    saw_opening = False
    while cursor < min(len(lines), h1_idx + 25):
        line = lines[cursor]
        if _OPENING_LINE.match(line):
            saw_opening = True
            insert_at = cursor + 1
        elif saw_opening and line.strip() == "":
            insert_at = cursor
            break
        elif not saw_opening and line.strip() == "" and cursor == h1_idx + 1:
            insert_at = cursor + 1
        cursor += 1

    rel = path.relative_to(DOCS)
    nav = _nav_for(rel)
    new_lines = lines[:insert_at] + ["", nav] + lines[insert_at:]
    new_text = "\n".join(new_lines)
    if not new_text.endswith("\n"):
        new_text += "\n"
    path.write_text(new_text, encoding="utf-8")
    return True


def main() -> int:
    changed = 0
    for path in sorted(DOCS.rglob("*.md")):
        rel = path.relative_to(DOCS)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        if _insert_nav(path):
            print(f"OK: nav added to {rel}")
            changed += 1
    print(f"INFO: {changed} files updated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
