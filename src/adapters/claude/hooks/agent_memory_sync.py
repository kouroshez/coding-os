#!/usr/bin/env python3
"""Render Trusted lessons into .agents/memory/MEMORY.md and harvest foreign notes."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

_PHYSICAL = Path(__file__).resolve()
_THINKING_OS = _PHYSICAL.parents[3] / "core" / "thinking_os"
if _THINKING_OS.is_dir() and str(_THINKING_OS) not in sys.path:
    sys.path.insert(0, str(_THINKING_OS))

GENERATED_START = "<!-- cos:generated:start — do not edit or re-import; source: coding-os DB -->"
GENERATED_END = "<!-- cos:generated:end -->"
GENERATED_BLOCK_RE = re.compile(
    r"<!-- cos:generated:start.*?-->.*?<!-- cos:generated:end -->", re.DOTALL
)
MAX_GENERATED_LINES = 200
LEDGER_NAME = ".harvested.json"


def _trusted_lessons(conn) -> list[dict]:
    rows = conn.execute(
        "SELECT pattern, times_validated FROM learned_patterns "
        "WHERE confidence >= 0.7 AND times_validated >= 3 "
        "AND COALESCE(memory_type, '') != 'stat' AND promoted_to IS NULL "
        "ORDER BY confidence * COALESCE(impact_score, 0.5) DESC "
        "LIMIT 60"
    ).fetchall()
    return [dict(r) for r in rows]


def render_mirror(memory_dir: Path, lessons: list[dict]) -> None:
    from sanitizer import redact_secrets

    lines = [GENERATED_START, "## Trusted lessons (auto-generated)", ""]
    for lesson in lessons:
        text, _ = redact_secrets((lesson["pattern"] or "").strip())
        lines.append(f"- {text} _(validated {lesson['times_validated']}×)_")
        if len(lines) >= MAX_GENERATED_LINES - 1:
            break
    lines.append(GENERATED_END)
    block = "\n".join(lines)

    memory_md = memory_dir / "MEMORY.md"
    existing = memory_md.read_text(encoding="utf-8", errors="replace") if memory_md.exists() else ""
    if GENERATED_BLOCK_RE.search(existing):
        updated = GENERATED_BLOCK_RE.sub(lambda _: block, existing, count=1)
    elif existing.strip():
        updated = f"{block}\n\n{existing}"
    else:
        updated = block + "\n"
    memory_md.write_text(updated, encoding="utf-8")


def _foreign_sections(memory_dir: Path) -> list[str]:
    sections: list[str] = []
    for md_file in sorted(memory_dir.glob("*.md")):
        text = md_file.read_text(encoding="utf-8", errors="replace")
        text = GENERATED_BLOCK_RE.sub("", text)
        for chunk in re.split(r"\n(?=## )", text):
            chunk = chunk.strip()
            # A harvestable note needs a heading AND a body — bare index
            # headers, frontmatter and link lists carry no lesson.
            if len(chunk) < 100 or "\n" not in chunk or chunk.startswith("---"):
                continue
            sections.append(chunk[:2000])
    return sections


def harvest(memory_dir: Path, conn) -> int:
    from tools.learning import _upsert_pattern

    ledger_path = memory_dir / LEDGER_NAME
    try:
        seen = set(json.loads(ledger_path.read_text(encoding="utf-8")))
    except Exception:
        seen = set()

    minted = 0
    for section in _foreign_sections(memory_dir):
        digest = hashlib.sha256(section.encode()).hexdigest()[:16]
        if digest in seen:
            continue
        seen.add(digest)
        result = _upsert_pattern(
            conn,
            pattern=section.split("\n", 1)[0].lstrip("# ").strip()[:300],
            memory_type="pattern",
            domain=None,
            source="import",
            confidence=0.5,
            concepts=json.dumps(["import", "agents-memory"]),
        )
        if result.get("id"):
            minted += 1
    conn.commit()
    ledger_path.write_text(json.dumps(sorted(seen), indent=0), encoding="utf-8")
    return minted


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        return 0
    db_path, memory_dir_raw = argv[1], argv[2]
    memory_dir = Path(memory_dir_raw)
    if not Path(db_path).exists():
        return 0
    memory_dir.mkdir(parents=True, exist_ok=True)

    from database import get_connection

    conn = get_connection(db_path)
    try:
        minted = harvest(memory_dir, conn)
        render_mirror(memory_dir, _trusted_lessons(conn))
        print(f"agent-memory sync: mirror rendered, {minted} foreign note(s) harvested")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv))
    except Exception:
        sys.exit(0)
