"""Tests for cos_task_move reviewer_check_required hint (TASK-004 G6).

Verifies that when:
  - cos_task_move transitions a task to status=complete, AND
  - .intent.json shows exhaustive=true, AND
  - An active audit-*.md exists with matching task_id in frontmatter

the response includes data.reviewer_check_required=True and a
data.reviewer_hint dict the main agent uses to spawn an Explore
subagent. Otherwise the hint is absent.
"""

from __future__ import annotations

import importlib.util
import json
import sqlite3
from pathlib import Path

import pytest
import yaml


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

from core.board_os import mcp_tools


@pytest.fixture
def project(tmp_path: Path, monkeypatch) -> tuple[Path, Path]:
    (tmp_path / ".coding-os").mkdir()
    (tmp_path / ".coding-os" / "scrumban-config.yaml").write_text(
        yaml.safe_dump(
            {
                "swimlanes": [
                    {"id": "core", "label": "Core", "color": "#3b82f6"},
                ],
                "wip_limits": {"in_progress": 5, "testing": 5, "emergency": 2},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "docs" / "tasks").mkdir(parents=True)
    agent_dir = tmp_path / ".coding-os" / "claude"
    agent_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("COS_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("COS_STATE_DIR", str(tmp_path / ".coding-os"))
    monkeypatch.setenv("COS_AGENT", "claude")
    monkeypatch.setenv("COS_AGENT_DIR", str(agent_dir))
    monkeypatch.chdir(tmp_path)
    return tmp_path, agent_dir


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    return db.init_db(tmp_path / "coding-os.db")


def _make_audit(
    repo_root: Path, task_id: str, status: str = "in_progress", slug: str = "test"
) -> Path:
    audit_dir = repo_root / "docs" / "tasks" / "audits"
    audit_dir.mkdir(parents=True, exist_ok=True)
    p = audit_dir / f"audit-{slug}.md"
    p.write_text(f"---\naudit_id: {slug}\ntask_id: {task_id}\nstatus: {status}\n---\n# audit\n")
    return p


def _write_intent(agent_dir: Path, exhaustive: bool, predicates: list[str]) -> None:
    (agent_dir / ".intent.json").write_text(
        json.dumps({"exhaustive": exhaustive, "predicates": predicates})
    )


def _create_and_progress(conn: sqlite3.Connection) -> str:
    env = json.loads(
        mcp_tools.cos_task_create(
            conn,
            title="hint test",
            swimlane="core",
            kind="feature",
            priority="P2",
            appetite="1d",
        )
    )
    assert env["ok"], env
    tid = env["data"]["task_id"]
    json.loads(
        mcp_tools.cos_task_move(conn, task_id=tid, to="in_progress", force=True, bypass_gates=True)
    )
    return tid


def _move_to_complete(conn: sqlite3.Connection, tid: str) -> dict:
    return json.loads(
        mcp_tools.cos_task_move(conn, task_id=tid, to="complete", force=True, bypass_gates=True)
    )


class TestReviewerHintEmitted:
    def test_hint_on_complete_with_exhaustive_intent_and_audit(self, project, conn) -> None:
        root, agent_dir = project
        tid = _create_and_progress(conn)
        _make_audit(root, task_id=tid)
        _write_intent(agent_dir, exhaustive=True, predicates=["coverage_100"])
        env = _move_to_complete(conn, tid)
        assert env["ok"] is True, env
        data = env["data"]
        assert data["new_status"] == "complete"
        assert data.get("reviewer_check_required") is True
        hint = data.get("reviewer_hint")
        assert hint is not None
        assert hint["subagent_type"] == "Explore"
        assert hint["substitutions"]["TASK_ID"] == tid
        assert "audit-test.md" in hint["substitutions"]["AUDIT_FILE"]
        assert hint["substitutions"]["PREDICATES"] == ["coverage_100"]


class TestReviewerHintAbsent:
    def test_no_hint_when_no_intent(self, project, conn) -> None:
        root, _ = project
        tid = _create_and_progress(conn)
        _make_audit(root, task_id=tid)
        env = _move_to_complete(conn, tid)
        assert "reviewer_check_required" not in env["data"]

    def test_no_hint_when_intent_non_exhaustive(self, project, conn) -> None:
        root, agent_dir = project
        tid = _create_and_progress(conn)
        _make_audit(root, task_id=tid)
        _write_intent(agent_dir, exhaustive=False, predicates=[])
        env = _move_to_complete(conn, tid)
        assert "reviewer_check_required" not in env["data"]

    def test_no_hint_when_no_active_audit(self, project, conn) -> None:
        _, agent_dir = project
        tid = _create_and_progress(conn)
        _write_intent(agent_dir, exhaustive=True, predicates=["coverage_100"])
        env = _move_to_complete(conn, tid)
        assert "reviewer_check_required" not in env["data"]

    def test_no_hint_when_audit_belongs_to_other_task(self, project, conn) -> None:
        root, agent_dir = project
        tid = _create_and_progress(conn)
        _make_audit(root, task_id="TASK-999", slug="other")
        _write_intent(agent_dir, exhaustive=True, predicates=["coverage_100"])
        env = _move_to_complete(conn, tid)
        assert "reviewer_check_required" not in env["data"]

    def test_no_hint_when_audit_status_completed(self, project, conn) -> None:
        root, agent_dir = project
        tid = _create_and_progress(conn)
        _make_audit(root, task_id=tid, status="completed")
        _write_intent(agent_dir, exhaustive=True, predicates=["coverage_100"])
        env = _move_to_complete(conn, tid)
        assert "reviewer_check_required" not in env["data"]
