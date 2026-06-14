"""Dependency-readiness reconciler (TASK-415) — the nightly job that closes the
gaps board_os.cascade_ready_dependents cannot reach (it fires only when one dep
completes). Three branches: re-block reopened deps, surface unblocked-but-
unauthored, surface long-blocked. Fixtures mirror board_os/tests/test_dependency_gate.
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
import time
from pathlib import Path

import pytest
import yaml

# Repo root (for `core.*` imports) + thinking_os (for v37's bare `from sanitizer
# import`, the thinking_os in-package convention) — mirrors board_os conftest.
_CORE = Path(__file__).resolve().parents[2]
_REPO_ROOT = Path(__file__).resolve().parents[3]
_THINKING_OS = _CORE / "thinking_os"
for _p in (_REPO_ROOT, _CORE, _THINKING_OS):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

try:
    from core.board_os import mcp_tools
    from core.scheduled.dep_reconcile import run_dep_reconcile
    from core.thinking_os import database as db
except ImportError:  # runner path differences
    from board_os import mcp_tools
    from scheduled.dep_reconcile import run_dep_reconcile
    from thinking_os import database as db


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


def _complete(conn: sqlite3.Connection, task_id: str) -> None:
    assert _parse(
        mcp_tools.cos_task_move(conn, task_id=task_id, to="in_progress", force=True)
    )["ok"]
    assert _parse(
        mcp_tools.cos_task_move(conn, task_id=task_id, to="complete", force=True)
    )["ok"]


def _status(conn: sqlite3.Connection, task_id: str) -> str:
    return _parse(mcp_tools.cos_task_show(conn, task_id=task_id))["data"]["status"]


# ── (a) re-block a ready task when its completed dependency reopens ──────────


def test_reblocks_when_dependency_reopens(project: Path, conn: sqlite3.Connection):
    dep_id, _ = _create(conn, project, title="prerequisite")
    task_id, task_path = _create(
        conn, project, title="dependent", depends_on=[dep_id], ready=True
    )
    _fill_dor(task_path)
    mcp_tools.sync_one(conn, task_path, project_root=project)

    _complete(conn, dep_id)  # dependent is now runnable, ready, in icebox
    assert _status(conn, task_id) == "icebox"

    # The dependency reopens (reverted out of complete).
    assert _parse(
        mcp_tools.cos_task_move(conn, task_id=dep_id, to="in_progress", force=True)
    )["ok"]

    result = run_dep_reconcile(conn, dry_run=False)
    assert result["status"] == "ok"
    reblocked_ids = {r["task_id"] for r in result["reblocked"]}
    assert task_id in reblocked_ids
    reason = next(r["reason"] for r in result["reblocked"] if r["task_id"] == task_id)
    assert dep_id in reason  # the reason names the reopened dependency
    assert _status(conn, task_id) == "blocked"


def test_does_not_reblock_when_deps_still_complete(project: Path, conn: sqlite3.Connection):
    dep_id, _ = _create(conn, project, title="prerequisite")
    task_id, task_path = _create(
        conn, project, title="dependent", depends_on=[dep_id], ready=True
    )
    _fill_dor(task_path)
    mcp_tools.sync_one(conn, task_path, project_root=project)
    _complete(conn, dep_id)  # dep stays complete

    result = run_dep_reconcile(conn, dry_run=False)
    assert task_id not in {r["task_id"] for r in result["reblocked"]}
    assert _status(conn, task_id) == "icebox"


# ── (b) surface unblocked-but-unauthored via the reused cascade ─────────────


def test_surfaces_unblocked_but_unauthored(project: Path, conn: sqlite3.Connection):
    dep_id, _ = _create(conn, project, title="prerequisite")
    # Dependent left with the create-stub body (DoR incomplete). Drive the dep
    # complete with the cascade SUPPRESSED so the reconciler is what surfaces it.
    dependent_id, _ = _create(conn, project, title="unauthored dependent", depends_on=[dep_id])
    import core.board_os.mcp_tools as _m  # noqa: PLC0415

    orig = _m._cascade_ready_dependents_safe
    _m._cascade_ready_dependents_safe = lambda *a, **k: {
        "readied": [],
        "needs_authoring": [],
        "still_blocked": [],
    }
    try:
        _complete(conn, dep_id)
    finally:
        _m._cascade_ready_dependents_safe = orig

    result = run_dep_reconcile(conn, dry_run=False)
    authoring_ids = {item["task_id"] for item in result["needs_authoring"]}
    assert dependent_id in authoring_ids


# ── (c) surface a task blocked longer than the review threshold ─────────────


def test_surfaces_long_blocked(project: Path, conn: sqlite3.Connection):
    task_id, _ = _create(conn, project, title="stuck")
    assert _parse(
        mcp_tools.cos_task_move(conn, task_id=task_id, to="blocked", force=True)
    )["ok"]
    # Backdate the blocked transition past the 14-day threshold.
    old = int(time.time()) - 20 * 86400
    conn.execute(
        "UPDATE task_status_history SET transitioned_at = ? "
        "WHERE task_id = ? AND new_status = 'blocked'",
        (old, task_id),
    )
    conn.commit()

    result = run_dep_reconcile(conn, dry_run=False)
    surfaced = {item["task_id"] for item in result["long_blocked"]}
    assert task_id in surfaced
    days = next(i["blocked_days"] for i in result["long_blocked"] if i["task_id"] == task_id)
    assert days >= 14


def test_recent_block_not_surfaced(project: Path, conn: sqlite3.Connection):
    task_id, _ = _create(conn, project, title="freshly blocked")
    assert _parse(
        mcp_tools.cos_task_move(conn, task_id=task_id, to="blocked", force=True)
    )["ok"]

    result = run_dep_reconcile(conn, dry_run=False)
    assert task_id not in {i["task_id"] for i in result["long_blocked"]}


# ── guards ──────────────────────────────────────────────────────────────────


def test_skips_when_no_tasks_table(tmp_path: Path):
    raw = sqlite3.connect(str(tmp_path / "empty.db"))
    try:
        result = run_dep_reconcile(raw, dry_run=False)
        assert result["status"] == "skipped"
    finally:
        raw.close()


def test_dry_run_does_not_mutate(project: Path, conn: sqlite3.Connection):
    dep_id, _ = _create(conn, project, title="prerequisite")
    task_id, task_path = _create(
        conn, project, title="dependent", depends_on=[dep_id], ready=True
    )
    _fill_dor(task_path)
    mcp_tools.sync_one(conn, task_path, project_root=project)
    _complete(conn, dep_id)
    mcp_tools.cos_task_move(conn, task_id=dep_id, to="in_progress", force=True)

    run_dep_reconcile(conn, dry_run=True)
    assert _status(conn, task_id) == "icebox", "dry-run must not re-block"
