"""Move misplaced `> Nav:` lines to AFTER the full opening block.

Usage:
    python scripts/dev/fix_nav_placement.py            # dry-run (default)
    python scripts/dev/fix_nav_placement.py --apply    # write changes

Exit codes:
    0  — nothing to fix, or `--apply` succeeded
    1  — dry-run found files that would change (CI signal)
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent.parent
DOCS = (REPO / "docs").resolve()
SKIP_DIRS = {"governance", "code-os-core-docs"}

_NAV = re.compile(r"^>\s*Nav:")
_OPENING_LINE = re.compile(r"^(Purpose:|Read when:|Skip when:|Read next:|>\s*[PRSN]:)")


def _plan(path: Path) -> str | None:
    """Return the fixed text if the file needs repair, else None."""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    nav_idx = next((i for i, ln in enumerate(lines[:30]) if _NAV.match(ln)), None)
    if nav_idx is None:
        return None

    last_opening_idx = None
    for i, ln in enumerate(lines[:30]):
        if _OPENING_LINE.match(ln):
            last_opening_idx = i

    if last_opening_idx is None or last_opening_idx < nav_idx:
        return None

    nav_line = lines[nav_idx]
    new_lines = lines[:nav_idx] + lines[nav_idx + 1 :]
    if nav_idx < len(new_lines) and new_lines[nav_idx].strip() == "":
        new_lines = new_lines[:nav_idx] + new_lines[nav_idx + 1 :]

    last_opening_idx = None
    for i, ln in enumerate(new_lines[:30]):
        if _OPENING_LINE.match(ln):
            last_opening_idx = i
    if last_opening_idx is None:
        return None

    head = new_lines[: last_opening_idx + 1]
    tail = new_lines[last_opening_idx + 1 :]
    while tail and tail[0].strip() == "":
        tail = tail[1:]
    fixed = [*head, "", nav_line, "", *tail]

    new_text = "\n".join(fixed)
    if not new_text.endswith("\n"):
        new_text += "\n"
    return new_text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Move misplaced > Nav: lines to AFTER the opening block."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write changes to disk. Default: dry-run, exit 1 if changes pending.",
    )
    args = parser.parse_args(argv)

    pending: list[tuple[Path, str]] = []
    for path in sorted(DOCS.rglob("*.md")):
        rel = path.relative_to(DOCS)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        fixed = _plan(path)
        if fixed is not None:
            pending.append((path, fixed))

    if not pending:
        print("OK: no nav placement issues")
        return 0

    if args.apply:
        for path, text in pending:
            path.write_text(text, encoding="utf-8")
            print(f"OK: nav fixed in {path.relative_to(REPO)}")
        print(f"WROTE: {len(pending)} files updated")
        return 0

    for path, _ in pending:
        print(f"PLAN: {path.relative_to(REPO)}")
    print(f"\nDRY-RUN: {len(pending)} files would change. Re-run with --apply to write.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
