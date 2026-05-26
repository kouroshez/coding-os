"""Tests for core.board_os.workflow — L.2 state machine + WIP + cycles."""

from __future__ import annotations

import importlib.util
import json
import sqlite3
import time
from pathlib import Path

import pytest

from core.board_os.config import ScrumbanConfig, Swimlane, WipLimits
from core.board_os.sync import sync_all
from core.board_os.workflow import (
    check_wip,
    patch_task_frontmatter_scalars,
    transition,
    validate_dependencies_no_cycle,
)


def _load_db_module():
    spec = importlib.util.spec_from_file_location(
        "_db_under_test",
        Path(__file__).resolve().parents[2] / "thinking_os" / "database.py",
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


db = _load_db_module()


def _make_config(in_progress: int = 1, testing: int = 3, emergency: int = 2):
    return ScrumbanConfig(
        swimlanes=(Swimlane(id="core", label="Core", color="#3b82f6"),),
        wip_limits=WipLimits(
            in_progress=in_progress,
            testing=testing,
            emergency=emergency,
        ),
    )


def _insert_task(
    conn: sqlite3.Connection,
    task_id: str,
    *,
    status: str = "icebox",
    swimlane: str = "core",
    depends_on: list[str] | None = None,
) -> None:
    conn.execute(
        "INSERT INTO tasks (task_id, title, status, file_path, content_hash, "
        "mtime, swimlane, kind, priority, appetite, labels_json, dependencies) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '[]', ?)",
        (
            task_id,
            f"test {task_id}",
            status,
            f"docs/tasks/{task_id}.md",
            "abc",
            int(time.time()),
            swimlane,
            "chore",
            "P2",
            "1h",
            json.dumps(depends_on or []),
        ),
    )
    conn.commit()


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    return db.init_db(tmp_path / "coding-os.db")


# ---------- Valid transitions ----------


@pytest.mark.parametrize(
    "from_status,to_status",
    [
        # "ready" has been folded into "icebox + label=ready" — the
        # pre-ready direct paths (icebox→in_progress, blocked→icebox)
        # are the new canonical flow.
        ("icebox", "in_progress"),
        ("icebox", "emergency"),
        ("emergency", "in_progress"),
        ("in_progress", "testing"),
        ("in_progress", "blocked"),
        ("in_progress", "complete"),
        ("in_progress", "icebox"),  # pull back to backlog w/out ready queue
        ("testing", "complete"),
        ("testing", "in_progress"),
        ("complete", "archive"),
        ("blocked", "in_progress"),
        ("blocked", "icebox"),
        # Un-archive recovery paths (soft-terminal):
        ("archive", "icebox"),
        ("archive", "complete"),
    ],
)
def test_transition_valid(conn: sqlite3.Connection, from_status, to_status):
    _insert_task(conn, "TASK-001", status=from_status)
    result = transition(
        conn,
        "TASK-001",
        to_status,
        config=_make_config(in_progress=10, testing=10, emergency=10),
    )
    assert result.ok, result.error
    assert result.previous_status == from_status
    assert result.new_status == to_status


def test_force_bypasses_invalid_transition(conn: sqlite3.Connection):
    """archive → testing is NOT in the state machine; force=True must allow it
    and record a forced-transition warning so the audit trail stays honest."""
    _insert_task(conn, "TASK-F1", status="archive")
    normal = transition(conn, "TASK-F1", "testing")
    assert normal.ok is False
    assert "invalid transition" in (normal.error or "")

    forced = transition(
        conn,
        "TASK-F1",
        "testing",
        force=True,
        config=_make_config(in_progress=10, testing=10, emergency=10),
    )
    assert forced.ok, forced.error
    assert forced.previous_status == "archive"
    assert forced.new_status == "testing"
    assert any("forced-transition" in w for w in forced.warnings)


def test_force_bypasses_wip_cap(conn: sqlite3.Connection):
    """force=True is a superset of bypass_wip — a single flag covers both."""
    _insert_task(conn, "TASK-F2", status="icebox")
    _insert_task(conn, "TASK-F3", status="in_progress")  # already at cap=1
    blocked = transition(
        conn,
        "TASK-F2",
        "in_progress",
        config=_make_config(in_progress=1),
    )
    assert blocked.ok is False
    assert "WIP cap" in (blocked.error or "")

    forced = transition(
        conn,
        "TASK-F2",
        "in_progress",
        force=True,
        config=_make_config(in_progress=1),
    )
    assert forced.ok, forced.error
    assert forced.new_status == "in_progress"


# ---------- Invalid transitions ----------


@pytest.mark.parametrize(
    "from_status,to_status",
    [
        # "ready" column no longer exists; rejections target real invalid
        # edges under the new state machine.
        ("icebox", "testing"),  # must pass through in_progress
        ("icebox", "complete"),  # no skipping the work
        ("archive", "in_progress"),  # archive → only {icebox, complete}
        ("complete", "in_progress"),  # complete only exits to archive
    ],
)
def test_transition_rejects_invalid(conn: sqlite3.Connection, from_status, to_status):
    _insert_task(conn, "TASK-002", status=from_status)
    result = transition(conn, "TASK-002", to_status)
    assert result.ok is False
    assert result.error_category == "validation"
    assert "invalid transition" in (result.error or "")


def test_transition_rejects_unknown_status(conn: sqlite3.Connection):
    _insert_task(conn, "TASK-003", status="icebox")
    result = transition(conn, "TASK-003", "nonsense")
    assert result.ok is False
    assert result.error_category == "validation"


def test_transition_missing_task_returns_not_found(conn: sqlite3.Connection):
    result = transition(conn, "TASK-MISSING", "icebox")
    assert result.ok is False
    assert result.error_category == "not_found"


def test_transition_no_op_same_status(conn: sqlite3.Connection):
    _insert_task(conn, "TASK-004", status="icebox")
    result = transition(conn, "TASK-004", "icebox")
    assert result.ok is True
    assert "no-op" in result.warnings[0]


# ---------- Optimistic concurrency ----------


def test_transition_optimistic_concurrency_detects_drift(conn: sqlite3.Connection):
    _insert_task(conn, "TASK-005", status="icebox")
    result = transition(
        conn,
        "TASK-005",
        "in_progress",
        expected_from="in_progress",
        config=_make_config(in_progress=10),
    )
    assert result.ok is False
    assert result.error_category == "transient"


def test_transition_optimistic_concurrency_accepts_match(conn: sqlite3.Connection):
    _insert_task(conn, "TASK-006", status="icebox")
    result = transition(
        conn,
        "TASK-006",
        "in_progress",
        expected_from="icebox",
        config=_make_config(in_progress=10),
    )
    assert result.ok is True


# ---------- WIP enforcement ----------


def test_wip_cap_blocks_second_in_progress(conn: sqlite3.Connection):
    _insert_task(conn, "TASK-010", status="in_progress")
    _insert_task(conn, "TASK-011", status="icebox")
    config = _make_config(in_progress=1)
    result = transition(conn, "TASK-011", "in_progress", config=config)
    assert result.ok is False
    assert "WIP cap" in (result.error or "")


def test_wip_cap_allows_within_limit(conn: sqlite3.Connection):
    _insert_task(conn, "TASK-012", status="icebox")
    config = _make_config(in_progress=1)
    result = transition(conn, "TASK-012", "in_progress", config=config)
    assert result.ok is True


def test_wip_bypass_flag_overrides_cap(conn: sqlite3.Connection):
    _insert_task(conn, "TASK-013", status="in_progress")
    _insert_task(conn, "TASK-014", status="icebox")
    config = _make_config(in_progress=1)
    result = transition(
        conn,
        "TASK-014",
        "in_progress",
        config=config,
        bypass_wip=True,
    )
    assert result.ok is True


def test_check_wip_reports_counts_and_caps(conn: sqlite3.Connection):
    _insert_task(conn, "TASK-020", status="in_progress")
    _insert_task(conn, "TASK-021", status="testing")
    _insert_task(conn, "TASK-022", status="testing")
    config = _make_config(in_progress=1, testing=3, emergency=2)
    state = check_wip(conn, config)
    assert state.counts["in_progress"] == 1
    assert state.counts["testing"] == 2
    assert state.counts["emergency"] == 0
    assert state.caps["testing"] == 3


# ---------- Dependency cycle detection (R-L-29) ----------


def test_no_cycle_is_empty(conn: sqlite3.Connection):
    _insert_task(conn, "TASK-030", depends_on=[])
    _insert_task(conn, "TASK-031", depends_on=["TASK-030"])
    cycles = validate_dependencies_no_cycle(conn, "TASK-032", ["TASK-031"])
    assert cycles == []


def test_direct_self_cycle_rejected(conn: sqlite3.Connection):
    _insert_task(conn, "TASK-040", depends_on=[])
    cycles = validate_dependencies_no_cycle(conn, "TASK-040", ["TASK-040"])
    assert cycles, f"expected cycle, got {cycles}"
    assert "TASK-040" in cycles[0]


def test_indirect_cycle_rejected(conn: sqlite3.Connection):
    _insert_task(conn, "TASK-050", depends_on=["TASK-051"])
    _insert_task(conn, "TASK-051", depends_on=[])
    cycles = validate_dependencies_no_cycle(conn, "TASK-051", ["TASK-050"])
    assert cycles
    assert "TASK-050" in cycles[0] and "TASK-051" in cycles[0]


# ---------- MD frontmatter atomic write ----------


def test_transition_updates_md_frontmatter(tmp_path: Path, conn: sqlite3.Connection):
    # Create a real MD file + sync it into DB first.
    (tmp_path / "docs" / "tasks").mkdir(parents=True)
    md = tmp_path / "docs" / "tasks" / "TASK-099-integration.md"
    md.write_text(
        "---\n"
        "id: TASK-099\n"
        'title: "integration"\n'
        "swimlane: core\n"
        "kind: chore\n"
        "status: icebox\n"
        "priority: P2\n"
        'appetite: "30m"\n'
        "---\n\n"
        "# TASK-099: integration\n\n"
        "**Outcome (one sentence):** frontmatter round-trips.\n\n"
        "## Acceptance\n"
        "- **Given** transition runs\n"
        "- **When** status changes\n"
        "- **Then** file updated\n",
        encoding="utf-8",
    )
    sync_all(conn, project_root=tmp_path)

    result = transition(
        conn,
        "TASK-099",
        "in_progress",
        config=_make_config(in_progress=5),
        agent_session="ses-claude-test",
        file_path=md,
    )
    assert result.ok, result.error

    updated = md.read_text(encoding="utf-8")
    assert "status: in_progress" in updated
    assert "agent_session: ses-claude-test" in updated
    assert "started:" in updated


def test_transition_complete_sets_completed_at(
    tmp_path: Path,
    conn: sqlite3.Connection,
):
    (tmp_path / "docs" / "tasks").mkdir(parents=True)
    md = tmp_path / "docs" / "tasks" / "TASK-100-complete.md"
    md.write_text(
        '---\nid: TASK-100\ntitle: "c"\nswimlane: core\nkind: chore\n'
        'status: testing\npriority: P2\nappetite: "30m"\n---\n\n# TASK-100: c\n',
        encoding="utf-8",
    )
    sync_all(conn, project_root=tmp_path)
    result = transition(conn, "TASK-100", "complete")
    assert result.ok, result.error
    row = conn.execute("SELECT completed_at FROM tasks WHERE task_id = 'TASK-100'").fetchone()
    assert row[0] is not None


def test_skip_testing_warning_emitted_on_shortcut(
    tmp_path: Path,
    conn: sqlite3.Connection,
):
    """in_progress→complete is legal but unconventional — the caller
    must see a warning so the human can record verification in the
    work log if intentional. Guards docs/governance/task-lifecycle.md
    Core Loop contract."""
    (tmp_path / "docs" / "tasks").mkdir(parents=True)
    md = tmp_path / "docs" / "tasks" / "TASK-200-skip.md"
    md.write_text(
        '---\nid: TASK-200\ntitle: "s"\nswimlane: core\nkind: chore\n'
        'status: in_progress\npriority: P2\nappetite: "30m"\n---\n\n# TASK-200: s\n',
        encoding="utf-8",
    )
    sync_all(conn, project_root=tmp_path)
    result = transition(conn, "TASK-200", "complete")
    assert result.ok, result.error
    assert any("skipped 'testing'" in w for w in result.warnings), (
        f"expected skip-testing warning; got: {result.warnings}"
    )


def test_no_skip_testing_warning_on_canonical_path(
    tmp_path: Path,
    conn: sqlite3.Connection,
):
    """testing→complete is the canonical path — must NOT emit the
    skip-testing warning. False positives here would train agents to
    ignore the signal."""
    (tmp_path / "docs" / "tasks").mkdir(parents=True)
    md = tmp_path / "docs" / "tasks" / "TASK-201-canon.md"
    md.write_text(
        '---\nid: TASK-201\ntitle: "c"\nswimlane: core\nkind: chore\n'
        'status: testing\npriority: P2\nappetite: "30m"\n---\n\n# TASK-201: c\n',
        encoding="utf-8",
    )
    sync_all(conn, project_root=tmp_path)
    result = transition(conn, "TASK-201", "complete")
    assert result.ok, result.error
    assert not any("skipped 'testing'" in w for w in result.warnings), (
        f"false-positive skip-testing warning on testing→complete: {result.warnings}"
    )


def test_patch_task_frontmatter_scalars_swimlane(tmp_path: Path):
    (tmp_path / "docs" / "tasks").mkdir(parents=True)
    md = tmp_path / "docs" / "tasks" / "TASK-101-swim.md"
    md.write_text(
        '---\nid: TASK-101\ntitle: "s"\nswimlane: core\nkind: chore\n'
        'status: icebox\npriority: P2\nappetite: "1d"\n---\n\n# TASK-101: s\n',
        encoding="utf-8",
    )
    patch_task_frontmatter_scalars(md, {"swimlane": "docs"})
    text = md.read_text(encoding="utf-8")
    assert "swimlane: docs" in text
    assert "status: icebox" in text
