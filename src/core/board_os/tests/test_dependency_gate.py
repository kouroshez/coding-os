"""Dependency-aware readiness — workflow gate + pick filter.

`depends_on` is load-bearing: with `workflow_policy.require_deps_complete`
(default on), `icebox → in_progress` is blocked (retryable `conflict`) while
any prerequisite is not `complete`; `cos_task_pick` omits such cards.
emergency and force bypass. Spec: docs/governance/task-lifecycle.md
§ Execution Rules (Dependency-aware readiness).
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

import pytest
import yaml

from core.board_os import mcp_tools
from core.thinking_os import database as db


@pytest.fixture
def project(tmp_path: Path, monkeypatch) -> Path:
    (tmp_path / ".coding-os").mkdir()
    (tmp_path / ".coding-os" / "scrumban-config.yaml").write_text(
        yaml.safe_dump(
            {
                "swimlanes": [{"id": "core", "label": "Core", "color": "#3b82f6"}],
                "wip_limits": {"in_progress": 5, "testing": 5, "emergency": 2},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "docs" / "tasks").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("COS_PROJECT_ROOT", str(tmp_path))
    return tmp_path


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    return db.init_db(tmp_path / "coding-os.db")


def _parse(envelope: str) -> dict:
    return json.loads(envelope)


def _create(conn: sqlite3.Connection, project: Path, **kw) -> tuple[str, Path]:
    env = _parse(mcp_tools.cos_task_create(conn, swimlane="core", kind="feature", **kw))
    assert env["ok"], env
    return env["data"]["task_id"], project / env["data"]["file_path"]


def _fill_dor(file_path: Path) -> None:
    body = file_path.read_text(encoding="utf-8")
    body = re.sub(
        r"\*\*Outcome \(one sentence\):\*\*\s*\(fill in[^\n]*",
        "**Outcome (one sentence):** Ship a real, well-scoped capability users asked for.",
        body,
    )
    body = body.replace(
        "- (no doc yet — exploratory)",
        "- [docs/governance/task-lifecycle.md](../governance/task-lifecycle.md)",
    )
    body = body.replace(
        "- **Given** ...\n- **When** ...\n- **Then** ...",
        "- **Given** a groomed task\n- **When** it is pulled\n- **Then** the gates pass.",
    )
    file_path.write_text(body, encoding="utf-8")


# ── (A) the icebox→in_progress dependency gate ────────────────────────────


def test_start_blocked_when_dependency_incomplete(project: Path, conn: sqlite3.Connection):
    dep_id, _ = _create(conn, project, title="prerequisite")  # icebox, not complete
    task_id, _ = _create(conn, project, title="dependent", depends_on=[dep_id], ready=True)

    env = _parse(mcp_tools.cos_task_move(conn, task_id=task_id, to="in_progress"))
    assert env["ok"] is False
    # `transient` is the MCP envelope's retryable-by-default category (a bare
    # `conflict` is non-retryable here) — re-issue once the dep completes.
    assert env["error"]["category"] == "transient"
    assert env["error"]["retryable"] is True
    assert dep_id in env["error"]["message"]


def test_start_allowed_once_dependency_complete(project: Path, conn: sqlite3.Connection):
    dep_id, _dep_path = _create(conn, project, title="prerequisite")
    task_id, task_path = _create(conn, project, title="dependent", depends_on=[dep_id], ready=True)
    _fill_dor(task_path)  # so the body DoR gate isn't what blocks the pull

    # Drive the prerequisite to complete (force bypasses its own gates).
    assert _parse(mcp_tools.cos_task_move(conn, task_id=dep_id, to="in_progress", force=True))["ok"]
    assert _parse(mcp_tools.cos_task_move(conn, task_id=dep_id, to="complete", force=True))["ok"]

    env = _parse(mcp_tools.cos_task_move(conn, task_id=task_id, to="in_progress"))
    assert env["ok"] is True, env
    assert env["data"]["new_status"] == "in_progress"


def test_start_allowed_with_force_despite_incomplete_dependency(
    project: Path, conn: sqlite3.Connection
):
    dep_id, _ = _create(conn, project, title="prerequisite")
    task_id, _ = _create(conn, project, title="dependent", depends_on=[dep_id], ready=True)

    env = _parse(mcp_tools.cos_task_move(conn, task_id=task_id, to="in_progress", force=True))
    assert env["ok"] is True, env
    assert env["data"]["new_status"] == "in_progress"


def test_emergency_lane_exempt_from_dependency_gate(project: Path, conn: sqlite3.Connection):
    dep_id, _ = _create(conn, project, title="prerequisite")  # stays incomplete
    task_id, task_path = _create(conn, project, title="urgent", depends_on=[dep_id])
    _fill_dor(task_path)  # so only the dependency gate could block — and it won't

    # icebox → emergency, then emergency → in_progress (the fast lane) succeeds
    # even though dep_id is still incomplete: the dep gate guards icebox pulls.
    assert _parse(mcp_tools.cos_task_move(conn, task_id=task_id, to="emergency", force=True))["ok"]
    env = _parse(mcp_tools.cos_task_move(conn, task_id=task_id, to="in_progress"))
    assert env["ok"] is True, env


# ── (C) cos_task_pick omits dep-incomplete cards ──────────────────────────


def test_pick_omits_dependency_incomplete_includes_runnable(
    project: Path, conn: sqlite3.Connection
):
    dep_id, _ = _create(conn, project, title="prerequisite", priority="P3")
    blocked_id, _ = _create(
        conn, project, title="blocked", depends_on=[dep_id], ready=True, priority="P0"
    )
    runnable_id, _ = _create(conn, project, title="runnable", ready=True, priority="P1")

    env = _parse(mcp_tools.cos_task_pick(conn))
    assert env["ok"] is True
    picked = {c["id"] for c in env["data"]["candidates"]}  # cards key on `id`
    assert runnable_id in picked
    assert blocked_id not in picked, "a card with an incomplete dependency is not runnable now"


def test_pick_surfaces_card_once_dependency_complete(project: Path, conn: sqlite3.Connection):
    dep_id, _ = _create(conn, project, title="prerequisite")
    blocked_id, _ = _create(
        conn, project, title="formerly blocked", depends_on=[dep_id], ready=True, priority="P0"
    )

    assert blocked_id not in {
        c["id"] for c in _parse(mcp_tools.cos_task_pick(conn))["data"]["candidates"]
    }

    mcp_tools.cos_task_move(conn, task_id=dep_id, to="in_progress", force=True)
    mcp_tools.cos_task_move(conn, task_id=dep_id, to="complete", force=True)

    picked = {c["id"] for c in _parse(mcp_tools.cos_task_pick(conn))["data"]["candidates"]}
    assert blocked_id in picked, "completing the prerequisite makes the card runnable"


def _complete(conn: sqlite3.Connection, task_id: str) -> dict:
    assert _parse(mcp_tools.cos_task_move(conn, task_id=task_id, to="in_progress", force=True))[
        "ok"
    ]
    env = _parse(mcp_tools.cos_task_move(conn, task_id=task_id, to="complete", force=True))
    assert env["ok"], env
    return env


def _labels(conn: sqlite3.Connection, task_id: str) -> list[str]:
    return _parse(mcp_tools.cos_task_show(conn, task_id=task_id))["data"].get("labels", [])


def _create_runnable(conn: sqlite3.Connection, project: Path, **kw) -> tuple[str, Path]:
    """A ready, DoR-complete icebox card — claim-next's transition gate passes."""
    task_id, path = _create(conn, project, ready=True, **kw)
    _fill_dor(path)
    mcp_tools.sync_one(conn, path, project_root=project)
    return task_id, path


# ── (B) completion cascade auto-readies unblocked, DoR-complete dependents ──


def test_completion_cascade_readies_unblocked_dependent(project: Path, conn: sqlite3.Connection):
    dep_id, _ = _create(conn, project, title="prerequisite")
    # A DoR-complete dependent in icebox WITHOUT the ready label yet.
    dependent_id, dependent_path = _create(conn, project, title="dependent", depends_on=[dep_id])
    _fill_dor(dependent_path)
    mcp_tools.sync_one(conn, dependent_path, project_root=project)
    assert "ready" not in _labels(conn, dependent_id)

    env = _complete(conn, dep_id)
    assert env["data"]["cascade"]["readied"] == [dependent_id]
    assert "ready" in _labels(conn, dependent_id), "cascade added the ready label"


def test_completion_cascade_surfaces_dor_incomplete_as_needs_authoring(
    project: Path, conn: sqlite3.Connection
):
    dep_id, _ = _create(conn, project, title="prerequisite")
    # Dependent left with the create-stub body (DoR incomplete) — must NOT be
    # auto-readied, but surfaced as needs-authoring rather than silently hidden.
    dependent_id, _ = _create(conn, project, title="unauthored dependent", depends_on=[dep_id])

    env = _complete(conn, dep_id)
    cascade = env["data"]["cascade"]
    assert dependent_id not in cascade["readied"]
    authoring_ids = {item["task_id"] for item in cascade["needs_authoring"]}
    assert dependent_id in authoring_ids
    assert "ready" not in _labels(conn, dependent_id)


def test_completion_cascade_leaves_multi_dep_dependent_blocked(
    project: Path, conn: sqlite3.Connection
):
    dep_a, _ = _create(conn, project, title="prereq A")
    dep_b, _ = _create(conn, project, title="prereq B")
    dependent_id, dependent_path = _create(
        conn, project, title="two-dep dependent", depends_on=[dep_a, dep_b]
    )
    _fill_dor(dependent_path)
    mcp_tools.sync_one(conn, dependent_path, project_root=project)

    # Completing only dep_a leaves dep_b open — dependent stays blocked.
    env = _complete(conn, dep_a)
    cascade = env["data"]["cascade"]
    assert dependent_id not in cascade["readied"]
    blocked_ids = {item["task_id"] for item in cascade["still_blocked"]}
    assert dependent_id in blocked_ids
    assert "ready" not in _labels(conn, dependent_id)

    # Completing dep_b now readies it.
    env = _complete(conn, dep_b)
    assert dependent_id in env["data"]["cascade"]["readied"]


# ── (E) atomic claim-next — distinct task per racing session, never twice ───


def test_claim_next_returns_a_runnable_task(project: Path, conn: sqlite3.Connection):
    runnable_id, _ = _create_runnable(conn, project, title="runnable", priority="P1")

    env = _parse(mcp_tools.cos_task_claim_next(conn, agent_session="ses-a"))
    assert env["ok"], env
    claimed = env["data"]["claimed"]
    assert claimed is not None
    assert claimed["id"] == runnable_id
    assert claimed["status"] == "in_progress"


def test_claim_next_excludes_dependency_blocked_card(project: Path, conn: sqlite3.Connection):
    dep_id, _ = _create(conn, project, title="prerequisite", priority="P3")
    _create(conn, project, title="blocked", depends_on=[dep_id], ready=True, priority="P0")

    # Only the dep-blocked P0 exists; it must not be claimable now.
    env = _parse(mcp_tools.cos_task_claim_next(conn, agent_session="ses-a"))
    assert env["ok"], env
    assert env["data"]["claimed"] is None


def test_claim_next_empty_board_returns_null(project: Path, conn: sqlite3.Connection):
    env = _parse(mcp_tools.cos_task_claim_next(conn, agent_session="ses-a"))
    assert env["ok"], env
    assert env["data"]["claimed"] is None


def test_concurrent_claim_next_yields_distinct_tasks(
    project: Path, conn: sqlite3.Connection, tmp_path: Path
):
    # Two runnable cards, two racing sessions: each must get a DISTINCT one,
    # never the same task twice. per_session_wip keeps each session's cap at 1.
    a_id, _ = _create_runnable(conn, project, title="task A", priority="P1")
    b_id, _ = _create_runnable(conn, project, title="task B", priority="P1")

    db_path = tmp_path / "coding-os.db"
    results: list[str | None] = []

    def claim(session: str) -> None:
        local = db.init_db(db_path)
        try:
            env = _parse(mcp_tools.cos_task_claim_next(local, agent_session=session))
            claimed = env["data"]["claimed"] if env["ok"] else None
            results.append(claimed["id"] if claimed else None)
        finally:
            local.close()

    import threading

    threads = [threading.Thread(target=claim, args=(f"ses-{i}",)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    claimed_ids = [r for r in results if r is not None]
    assert set(claimed_ids) <= {a_id, b_id}
    assert len(claimed_ids) == len(set(claimed_ids)), "no task claimed twice"


def test_concurrent_claim_next_single_task_one_winner_one_null(
    project: Path, conn: sqlite3.Connection, tmp_path: Path
):
    # One runnable card, two racing sessions: exactly ONE claim + one
    # {claimed: null}. The loser's compare-and-set misses and it walks off the
    # end of the candidates rather than double-claiming or raising.
    only_id, _ = _create_runnable(conn, project, title="the only task", priority="P1")

    db_path = tmp_path / "coding-os.db"
    results: list[str | None] = []

    def claim(session: str) -> None:
        local = db.init_db(db_path)
        try:
            env = _parse(mcp_tools.cos_task_claim_next(local, agent_session=session))
            assert env["ok"], env  # never raises, always a well-formed envelope
            claimed = env["data"]["claimed"]
            results.append(claimed["id"] if claimed else None)
        finally:
            local.close()

    import threading

    threads = [threading.Thread(target=claim, args=(f"ses-{i}",)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sorted(results, key=lambda r: r or "") == [None, only_id], results
