"""Tests for core.board_os.workflow — L.2 state machine + WIP + cycles."""

from __future__ import annotations

import importlib.util
import json
import sqlite3
import threading
import time
from pathlib import Path

import pytest

from core.board_os.config import ScrumbanConfig, Swimlane, WipLimits
from core.board_os.sync import sync_all
from core.board_os.workflow import (
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


def test_transition_restores_md_when_post_write_step_fails(
    tmp_path: Path, conn: sqlite3.Connection
):
    # Finding A: a successful (atomic) frontmatter write followed by a failing
    # later step must NOT leave the file ahead of the rolled-back DB. Drop
    # task_status_history so the history INSERT raises AFTER the MD write, then
    # assert the file is restored to its pre-transition status.
    (tmp_path / "docs" / "tasks").mkdir(parents=True)
    md = tmp_path / "docs" / "tasks" / "TASK-110-restore.md"
    md.write_text(
        "---\n"
        "id: TASK-110\n"
        'title: "restore"\n'
        "swimlane: core\n"
        "kind: chore\n"
        "status: icebox\n"
        "priority: P2\n"
        'appetite: "30m"\n'
        "labels: [ready]\n"
        "---\n\n"
        "# TASK-110: restore\n\n"
        "**Outcome (one sentence):** file is restored on failure.\n",
        encoding="utf-8",
    )
    sync_all(conn, project_root=tmp_path)
    conn.execute("DROP TABLE task_status_history")
    conn.commit()

    with pytest.raises(sqlite3.OperationalError):
        transition(
            conn,
            "TASK-110",
            "in_progress",
            config=_make_config(in_progress=5),
            agent_session="ses-claude-test",
            file_path=md,
        )

    assert "status: icebox" in md.read_text(encoding="utf-8")
    row = conn.execute("SELECT status FROM tasks WHERE task_id = ?", ("TASK-110",)).fetchone()
    assert row[0] == "icebox"


def test_transition_two_real_connections_exactly_one_wins(tmp_path: Path):
    # Real concurrency (not single-threaded drift simulation): two live
    # connections both attempt icebox->in_progress at a barrier. BEGIN
    # IMMEDIATE + the CAS UPDATE must let exactly one win.
    db_path = tmp_path / "coding-os.db"
    setup = db.init_db(db_path)
    _insert_task(setup, "TASK-120", status="icebox")
    setup.commit()
    setup.close()

    results: dict[str, object] = {}
    barrier = threading.Barrier(2)

    def claim(name: str) -> None:
        c = db.get_connection(db_path)
        try:
            barrier.wait()
            results[name] = transition(
                c,
                "TASK-120",
                "in_progress",
                config=_make_config(in_progress=10),
                agent_session=f"ses-claude-{name}",
            )
        finally:
            c.close()

    threads = [threading.Thread(target=claim, args=(n,)) for n in ("a", "b")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    winners = [r for r in results.values() if getattr(r, "ok", False)]
    assert len(winners) == 1, results

    final = db.get_connection(db_path)
    status = final.execute("SELECT status FROM tasks WHERE task_id = ?", ("TASK-120",)).fetchone()[
        0
    ]
    final.close()
    assert status == "in_progress"


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
