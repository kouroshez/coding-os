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
    _is_shared_pid_session,
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
    labels: list[str] | None = None,
    agent_session: str | None = None,
) -> None:
    # Default to a `ready`-labelled task: most state-machine/WIP tests
    # need a pullable task, matching the require_ready_label contract.
    # Pass labels=[] to exercise the not-ready path.
    labels = ["ready"] if labels is None else labels
    conn.execute(
        "INSERT INTO tasks (task_id, title, status, file_path, content_hash, "
        "mtime, swimlane, kind, priority, appetite, labels_json, dependencies, agent_session) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
            json.dumps(labels),
            json.dumps(depends_on or []),
            agent_session,
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
    # bypass_gates isolates this to pure state-machine edge validity —
    # the ready / testing policy gates are covered by their own tests.
    result = transition(
        conn,
        "TASK-001",
        to_status,
        config=_make_config(in_progress=10, testing=10, emergency=10),
        bypass_gates=True,
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


# ---------- Workflow-policy gates (ready + testing-before-complete) ----------


def test_ready_gate_blocks_unready_icebox(conn: sqlite3.Connection):
    _insert_task(conn, "TASK-RG1", status="icebox", labels=[])
    result = transition(conn, "TASK-RG1", "in_progress", config=_make_config(in_progress=10))
    assert result.ok is False
    assert result.error_category == "validation"
    assert "not ready" in (result.error or "")


def test_ready_gate_allows_ready_icebox(conn: sqlite3.Connection):
    _insert_task(conn, "TASK-RG2", status="icebox", labels=["ready"])
    result = transition(conn, "TASK-RG2", "in_progress", config=_make_config(in_progress=10))
    assert result.ok, result.error


def test_ready_gate_exempts_emergency_path(conn: sqlite3.Connection):
    # emergency→in_progress is the fast lane — no ready label required.
    _insert_task(conn, "TASK-RG3", status="emergency", labels=[])
    result = transition(conn, "TASK-RG3", "in_progress", config=_make_config(in_progress=10))
    assert result.ok, result.error


def test_ready_gate_skipped_without_config(conn: sqlite3.Connection):
    # DB-only path (config=None) must not enforce policy.
    _insert_task(conn, "TASK-RG4", status="icebox", labels=[])
    result = transition(conn, "TASK-RG4", "in_progress")
    assert result.ok, result.error


def test_testing_gate_blocks_in_progress_to_complete(conn: sqlite3.Connection):
    _insert_task(conn, "TASK-TG1", status="in_progress")
    result = transition(conn, "TASK-TG1", "complete", config=_make_config())
    assert result.ok is False
    assert result.error_category == "validation"
    assert "through testing" in (result.error or "")


def test_testing_gate_allows_testing_to_complete(conn: sqlite3.Connection):
    _insert_task(conn, "TASK-TG2", status="testing")
    result = transition(conn, "TASK-TG2", "complete", config=_make_config())
    assert result.ok, result.error


def test_testing_gate_force_overrides(conn: sqlite3.Connection):
    _insert_task(conn, "TASK-TG3", status="in_progress")
    result = transition(conn, "TASK-TG3", "complete", config=_make_config(), force=True)
    assert result.ok, result.error


# ---------- Per-session WIP (concurrent multi-agent) ----------


def test_per_session_wip_does_not_block_other_session(conn: sqlite3.Connection):
    # Session A holds an in_progress task; session B (different
    # agent_session) must still be able to start its own.
    _insert_task(conn, "TASK-PA", status="in_progress", agent_session="ses-A")
    _insert_task(conn, "TASK-PB", status="icebox", agent_session="ses-B")
    result = transition(
        conn,
        "TASK-PB",
        "in_progress",
        config=_make_config(in_progress=1),
        agent_session="ses-B",
    )
    assert result.ok, result.error


def test_per_session_wip_still_blocks_same_session(conn: sqlite3.Connection):
    # The same session is still capped at 1 (focus discipline).
    _insert_task(conn, "TASK-SA1", status="in_progress", agent_session="ses-A")
    _insert_task(conn, "TASK-SA2", status="icebox", agent_session="ses-A")
    result = transition(
        conn,
        "TASK-SA2",
        "in_progress",
        config=_make_config(in_progress=1),
        agent_session="ses-A",
    )
    assert result.ok is False
    assert "WIP cap" in (result.error or "")


def test_global_wip_when_per_session_disabled(conn: sqlite3.Connection):
    from core.board_os.config import ScrumbanConfig, Swimlane, WipLimits, WorkflowPolicy

    cfg = ScrumbanConfig(
        swimlanes=(Swimlane(id="core", label="Core", color="#3b82f6"),),
        wip_limits=WipLimits(in_progress=1),
        workflow_policy=WorkflowPolicy(per_session_wip=False),
    )
    _insert_task(conn, "TASK-GA", status="in_progress", agent_session="ses-A")
    _insert_task(conn, "TASK-GB", status="icebox", agent_session="ses-B")
    result = transition(conn, "TASK-GB", "in_progress", config=cfg, agent_session="ses-B")
    assert result.ok is False
    assert "WIP cap" in (result.error or "")


# ---------- Shared-PID WIP degradation detection (TASK-287) ----------


def test_is_shared_pid_session_detects_synthetic() -> None:
    # The resolve_agent_session last-resort synthetic — shared by all panels
    # of the long-lived MCP server — must be recognised.
    assert _is_shared_pid_session("ses-claude-pid12345") is True
    assert _is_shared_pid_session("ses-codex-pid7") is True
    # Genuine per-panel session ids and non-sessions must NOT match.
    assert _is_shared_pid_session("ses-claude-20260609-143642-c7c5") is False
    assert _is_shared_pid_session("ses-claude-pid12-extra") is False
    assert _is_shared_pid_session(None) is False
    assert _is_shared_pid_session("") is False


def test_shared_pid_session_warns_wip_degraded(conn: sqlite3.Connection, caplog) -> None:
    # A per-session cap keyed on the shared ses-<agent>-pid<PID> synthetic must
    # be surfaced (not silently applied as if it were panel-isolated).
    _insert_task(conn, "TASK-SP", status="in_progress", agent_session="ses-claude-pid99999")
    with caplog.at_level("WARNING"):
        check_wip(conn, _make_config(in_progress=1), agent_session="ses-claude-pid99999")
    assert "WIP cap degraded" in caplog.text
    assert "ses-claude-pid99999" in caplog.text


def test_real_session_no_wip_degraded_warning(conn: sqlite3.Connection, caplog) -> None:
    _insert_task(
        conn, "TASK-RS", status="in_progress", agent_session="ses-claude-20260609-143642-c7c5"
    )
    with caplog.at_level("WARNING"):
        check_wip(
            conn, _make_config(in_progress=1), agent_session="ses-claude-20260609-143642-c7c5"
        )
    assert "WIP cap degraded" not in caplog.text


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
        "labels: [ready]\n"
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
