"""Tests for core.board_os.parser — lean + legacy parsing."""

from __future__ import annotations

from core.board_os.parser import (
    ParsedTask,
    extract_frontmatter,
    is_lean_format,
    parse_task,
)

LEAN_FIXTURE = """---
id: TASK-199
title: "Implement Kuzu backend"
swimlane: graph_os
kind: feature
epic: phase-i
labels: [indexing, perf]
status: in_progress
priority: P1
appetite: "1d"
created: 2026-04-19
started: 2026-04-20
completed: null
agent_session: ses-claude-abc
depends_on: [TASK-180]
blocked_by: []
references: [TASK-045]
---

# TASK-199: Implement Kuzu backend

**Outcome (one sentence):** SQLite fallback swappable with Kuzu via config.

## Read First
- [docs/phase-i-knowledge-graph-plan.md](../phase-i.md) — backend architecture
- `core/graph_os/backend.py` — Protocol

## Acceptance (G/W/T)
- **Given** graph.backend: kuzu
- **When** cos_graph_context called
- **Then** parity with SQLite

## Work Log
- 2026-04-20 [claude]: schema loaded; 12/50 parity
- 2026-04-21 [claude]: HNSW wired; 35/50 green

## Rollback
Additive only. Revert commit.
"""

MALFORMED_YAML = """---
id: TASK-200
title: [unclosed
---

# TASK-200: broken
"""

LEGACY_12_SECTION = """<!-- domain:BACKEND | layer:task | ssot:true | updated:2026-01-01 -->
# TASK-088: [BACKEND] Old-style task

Purpose: Legacy test fixture.
Read when: Working on this task.

- Created: 2026-01-01

## Goal
Legacy goal text.

## Read First
- REF:BACKEND-API

## Source of Truth
- docs/prd/x.md

## Scope
### In
- stuff
### Out
- other stuff

## Requirements
- requirement 1

## Dependencies
- TASK-001
- TASK-002

## Open Questions
- none

## Rabbit Holes
- none

## Verification
- make test
"""


# ---------- Format detection ----------


def test_is_lean_format_true_for_frontmatter():
    assert is_lean_format(LEAN_FIXTURE) is True


def test_is_lean_format_false_for_legacy():
    assert is_lean_format(LEGACY_12_SECTION) is False


def test_is_lean_format_false_for_empty():
    assert is_lean_format("") is False


def test_is_lean_format_false_for_plain_h1():
    assert is_lean_format("# TASK-001: Just a header\n") is False


# ---------- Frontmatter extraction ----------


def test_extract_frontmatter_happy_path():
    fm = extract_frontmatter(LEAN_FIXTURE)
    assert fm is not None
    assert fm["id"] == "TASK-199"
    assert fm["swimlane"] == "graph_os"
    assert fm["kind"] == "feature"
    assert fm["labels"] == ["indexing", "perf"]


def test_extract_frontmatter_returns_none_on_bad_yaml():
    assert extract_frontmatter(MALFORMED_YAML) is None


def test_extract_frontmatter_returns_none_on_no_frontmatter():
    assert extract_frontmatter(LEGACY_12_SECTION) is None


# ---------- parse_task (lean) ----------


def test_parse_task_lean_full():
    parsed = parse_task(LEAN_FIXTURE)
    assert isinstance(parsed, ParsedTask)
    assert parsed.is_lean is True
    assert parsed.task_id == "TASK-199"
    assert parsed.title == "Implement Kuzu backend"
    assert parsed.swimlane == "graph_os"
    assert parsed.kind == "feature"
    assert parsed.epic == "phase-i"
    assert parsed.labels == ("indexing", "perf")
    assert parsed.status == "in_progress"
    assert parsed.priority == "P1"
    assert parsed.appetite == "1d"
    assert parsed.depends_on == ("TASK-180",)
    assert parsed.references == ("TASK-045",)
    assert parsed.agent_session == "ses-claude-abc"


def test_parse_task_extracts_outcome():
    parsed = parse_task(LEAN_FIXTURE)
    assert parsed is not None
    assert parsed.outcome is not None
    assert "SQLite fallback" in parsed.outcome


def test_parse_task_extracts_read_first_paths():
    parsed = parse_task(LEAN_FIXTURE)
    assert parsed is not None
    assert len(parsed.read_first) == 2
    assert parsed.read_first[0] == "../phase-i.md"
    assert parsed.read_first[1] == "core/graph_os/backend.py"


def test_parse_task_extracts_work_log_lines():
    parsed = parse_task(LEAN_FIXTURE)
    assert parsed is not None
    assert len(parsed.work_log_lines) == 2
    assert "12/50 parity" in parsed.work_log_lines[0]
    assert "35/50 green" in parsed.work_log_lines[1]


def test_parse_task_body_hash_is_deterministic():
    p1 = parse_task(LEAN_FIXTURE)
    p2 = parse_task(LEAN_FIXTURE)
    assert p1 is not None and p2 is not None
    assert p1.body_hash == p2.body_hash
    assert len(p1.body_hash) == 16


# ---------- parse_task (fallback) ----------


def test_parse_task_legacy_fallback_works():
    parsed = parse_task(LEGACY_12_SECTION)
    assert parsed is not None
    assert parsed.is_lean is False
    assert parsed.task_id == "TASK-088"
    assert parsed.title == "Old-style task"
    assert "TASK-001" in parsed.depends_on
    assert "TASK-002" in parsed.depends_on
    assert "legacy fallback" in parsed.parse_warnings[0]


def test_parse_task_bad_yaml_falls_back_to_legacy():
    """Broken YAML with legacy-parseable H1 returns a legacy ParsedTask."""
    parsed = parse_task(MALFORMED_YAML)
    # Legacy parser may succeed if H1 is well-formed — either None (strict) or
    # is_lean=False (fallback).  We accept both; the key invariant: never a
    # ParsedTask marked is_lean=True when frontmatter is malformed.
    if parsed is not None:
        assert parsed.is_lean is False


def test_parse_task_default_status_is_icebox_when_missing():
    """Lean file with no status → defaults to icebox."""
    minimal = """---
id: TASK-500
title: "minimal"
swimlane: backend
kind: chore
---

# TASK-500: minimal
"""
    parsed = parse_task(minimal)
    assert parsed is not None
    assert parsed.status == "icebox"


# ---------- Validation warnings ----------


def test_parse_task_warns_on_unknown_kind():
    bad_kind = """---
id: TASK-501
title: "bad"
swimlane: backend
kind: someinventedtype
status: icebox
priority: P2
---

# TASK-501: bad
"""
    parsed = parse_task(bad_kind)
    assert parsed is not None
    assert any("KIND_ENUM" in w for w in parsed.parse_warnings)


def test_parse_task_warns_on_label_colliding_with_kind_enum():
    colliding = """---
id: TASK-502
title: "collide"
swimlane: backend
kind: feature
labels: [bug]
status: icebox
priority: P2
---

# TASK-502: collide
"""
    parsed = parse_task(colliding)
    assert parsed is not None
    assert any("collides with KIND_ENUM" in w for w in parsed.parse_warnings)


# ---------- Persian / Unicode ----------


def test_parse_task_persian_title():
    persian = """---
id: TASK-600
title: "پیاده‌سازی بک‌اند"
swimlane: backend
kind: feature
status: icebox
priority: P2
---

# TASK-600: پیاده‌سازی بک‌اند

**Outcome (one sentence):** کاربر می‌تواند وارد شود.
"""
    parsed = parse_task(persian)
    assert parsed is not None
    assert parsed.title == "پیاده‌سازی بک‌اند"
    assert parsed.outcome is not None
    assert "کاربر" in parsed.outcome
