"""Move misplaced `> Nav:` lines to AFTER the full opening block."""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
DOCS = REPO / "docs"
SKIP_DIRS = {"governance", "code-os-core-docs"}

_NAV = re.compile(r"^>\s*Nav:")
_OPENING_LINE = re.compile(r"^(Purpose:|Read when:|Skip when:|Read next:|>\s*[PRSN]:)")


def _fix(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    # Find the Nav line.
    nav_idx = next((i for i, ln in enumerate(lines[:30]) if _NAV.match(ln)), None)
    if nav_idx is None:
        return False

    # Find the last opening-block line in the first 30 lines.
    last_opening_idx = None
    for i, ln in enumerate(lines[:30]):
        if _OPENING_LINE.match(ln):
            last_opening_idx = i

    if last_opening_idx is None or last_opening_idx < nav_idx:
        # Either no opening block, or Nav already after it — nothing to do.
        return False

    # Pull the Nav line out and reinsert after the last opening line.
    nav_line = lines[nav_idx]
    # Remove the Nav line and any duplicated blank line right after it.
    new_lines = lines[:nav_idx] + lines[nav_idx + 1 :]
    if nav_idx < len(new_lines) and new_lines[nav_idx].strip() == "":
        new_lines = new_lines[:nav_idx] + new_lines[nav_idx + 1 :]

    # Recompute last_opening_idx in the new list (it may have shifted up by 1 if
    # Nav was before it).
    last_opening_idx = None
    for i, ln in enumerate(new_lines[:30]):
        if _OPENING_LINE.match(ln):
            last_opening_idx = i
    if last_opening_idx is None:
        return False

    # Insert blank + Nav + blank after the last opening line.
    head = new_lines[: last_opening_idx + 1]
    tail = new_lines[last_opening_idx + 1 :]
    while tail and tail[0].strip() == "":
        tail = tail[1:]
    fixed = head + ["", nav_line, ""] + tail

    new_text = "\n".join(fixed)
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
        if _fix(path):
            print(f"OK: nav fixed in {rel}")
            changed += 1
    print(f"INFO: {changed} files updated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
