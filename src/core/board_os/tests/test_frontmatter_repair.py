"""repair_duplicate_frontmatter — the durable fix for the recurring
prepended-block corruption that made sync_one reject a task file outright."""

from __future__ import annotations

from pathlib import Path

from board_os.parser import (
    detect_duplicate_frontmatter,
    extract_frontmatter,
    parse_task,
    repair_duplicate_frontmatter,
)

LIVE = """---
id: TASK-001
title: "Live"
swimlane: core
kind: bug
status: blocked
priority: P0
appetite: 1d
---
# TASK-001: Live

"""

STALE = """---
id: TASK-001
title: "Live"
swimlane: core
kind: bug
status: icebox
priority: P2
appetite: 1d
---

# TASK-001: Live

"""

BODY = """**Outcome (one sentence):** Something measurable.

## Read First
- `src/x.py`

## Acceptance (G/W/T)
- **Given** x **When** y **Then** z

## Work Log
"""


def _corrupted() -> str:
    return LIVE + STALE + BODY


def test_repair_drops_the_stale_block_and_keeps_the_live_one() -> None:
    fixed = repair_duplicate_frontmatter(_corrupted())
    assert fixed is not None
    assert detect_duplicate_frontmatter(fixed) is None
    front = extract_frontmatter(fixed)
    assert front["status"] == "blocked"
    assert front["priority"] == "P0"


def test_repair_preserves_the_body() -> None:
    fixed = repair_duplicate_frontmatter(_corrupted())
    assert "## Acceptance (G/W/T)" in fixed
    assert "Something measurable." in fixed
    assert fixed.count("# TASK-001: Live") == 1


def test_repaired_file_parses_and_would_sync(tmp_path: Path) -> None:
    fixed = repair_duplicate_frontmatter(_corrupted())
    path = tmp_path / "TASK-001-live.md"
    path.write_text(fixed, encoding="utf-8")
    parsed = parse_task(fixed, path=path)
    assert parsed is not None
    assert parsed.status == "blocked"
    assert parsed.priority == "P0"


def test_repair_is_a_noop_on_a_clean_file() -> None:
    assert repair_duplicate_frontmatter(LIVE + BODY) is None


def test_repair_is_idempotent() -> None:
    once = repair_duplicate_frontmatter(_corrupted())
    assert repair_duplicate_frontmatter(once) is None


def test_repair_ignores_a_yaml_snippet_that_is_not_frontmatter() -> None:
    body_with_rule = LIVE + "Some prose.\n\n---\n\nMore prose after a horizontal rule.\n"
    assert repair_duplicate_frontmatter(body_with_rule) is None
