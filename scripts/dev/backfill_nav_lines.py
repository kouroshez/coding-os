"""Insert `> Nav:` line after the opening block on docs missing it.

Usage:
    python scripts/dev/backfill_nav_lines.py            # dry-run, exit 1 if changes pending
    python scripts/dev/backfill_nav_lines.py --apply    # write changes

Exit codes:
    0  — nothing to do, or all writes succeeded
    1  — dry-run: at least one file would change
    2  — write failure
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
DOCS = (REPO / "docs").resolve()
SKIP_DIRS = {"governance", "code-os-core-docs"}

_FRONTMATTER = re.compile(r"^<!--\s*domain:.*-->\s*$")
_H1 = re.compile(r"^#\s+")
_NAV = re.compile(r"^>\s*Nav:")
_OPENING_LINE = re.compile(r"^(Purpose:|Read when:|Skip when:|Read next:|>\s*[PRSN]:)")


def _nav_for(rel: Path) -> str:
    parts = rel.parts
    if rel.name == "00-index.md" and len(parts) == 1:
        return "> Nav: [Repo](../README.md)"
    if rel.name == "00-index.md":
        return "> Nav: [Docs Index](../00-index.md)"
    if len(parts) > 1:
        return "> Nav: [Section Index](./00-index.md) | [Docs Index](../00-index.md)"
    return "> Nav: [Docs Index](./00-index.md)"


def _plan_nav(path: Path) -> str | None:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines:
        return None

    has_frontmatter = any(_FRONTMATTER.match(ln) for ln in lines[:3])
    h1_idx = next((i for i, ln in enumerate(lines[:5]) if _H1.match(ln)), None)
    if not has_frontmatter or h1_idx is None:
        return None

    if any(_NAV.match(ln) for ln in lines[: h1_idx + 20]):
        return None

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
    return new_text if new_text != text else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Insert > Nav: line on docs missing it.")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write changes to disk (default: dry-run, exit 1 if changes pending).",
    )
    args = parser.parse_args(argv)

    plans: list[tuple[Path, str]] = []
    for path in sorted(DOCS.rglob("*.md")):
        rel = path.relative_to(DOCS)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        new_text = _plan_nav(path)
        if new_text is not None:
            plans.append((path, new_text))
            print(f"PLAN: nav would be added to {rel}")

    if not plans:
        print("OK: no nav changes needed")
        return 0

    if not args.apply:
        print(f"\nDRY-RUN: {len(plans)} files would change. Re-run with --apply to write.")
        return 1

    written = 0
    for path, new_text in plans:
        try:
            path.write_text(new_text, encoding="utf-8")
            print(f"OK: nav added to {path.relative_to(DOCS)}")
            written += 1
        except OSError as exc:
            print(f"FAIL: cannot write {path.relative_to(DOCS)}: {exc}", file=sys.stderr)
    print(f"\nINFO: {written}/{len(plans)} files updated")
    return 0 if written == len(plans) else 2


if __name__ == "__main__":
    sys.exit(main())
