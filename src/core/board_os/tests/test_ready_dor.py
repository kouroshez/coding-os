"""DoR surfacing when marking a task `ready` (TASK-258).

`cos_task_ready` reuses the same validator the icebox→in_progress gate uses,
so a task can't be silently labeled `ready` while incomplete. Default = warn
(label set + `data.dor` lists gaps); `COS_READY_DOR=strict` refuses the label
unless `COS_DOR_OVERRIDE=1` + a valid `COS_OVERRIDE_REASON`.
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


def _make_feature(conn: sqlite3.Connection, project: Path) -> tuple[str, Path]:
    env = json.loads(
        mcp_tools.cos_task_create(conn, title="DoR demo feature", swimlane="core", kind="feature")
    )
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
        "- **Given** a groomed task\n- **When** it is marked ready\n- **Then** the DoR validator passes.",
    )
    file_path.write_text(body, encoding="utf-8")


def test_ready_warns_but_sets_label_when_dor_incomplete(project: Path, conn: sqlite3.Connection) -> None:
    task_id, _ = _make_feature(conn, project)
    env = json.loads(mcp_tools.cos_task_ready(conn, task_id=task_id))
    assert env["ok"] is True
    assert "ready" in env["data"]["labels"]  # warn-default still lands the label
    gaps = env["data"].get("dor")
    assert gaps, "a placeholder feature must surface DoR gaps"
    assert any(g["code"].startswith("DOR_") for g in gaps)


def test_ready_strict_blocks_incomplete_and_leaves_label_unset(
    project: Path, conn: sqlite3.Connection, monkeypatch
) -> None:
    monkeypatch.setenv("COS_READY_DOR", "strict")
    task_id, _ = _make_feature(conn, project)
    env = json.loads(mcp_tools.cos_task_ready(conn, task_id=task_id))
    assert env["ok"] is False
    assert env["error"]["category"] == "validation"
    row = conn.execute("SELECT labels_json FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
    assert "ready" not in (row[0] or ""), "strict refusal must not half-apply the label"


def test_ready_strict_override_sets_label(
    project: Path, conn: sqlite3.Connection, monkeypatch
) -> None:
    monkeypatch.setenv("COS_READY_DOR", "strict")
    monkeypatch.setenv("COS_DOR_OVERRIDE", "1")
    monkeypatch.setenv("COS_OVERRIDE_REASON", "groomed live in standup, DoR follow-up tracked")
    task_id, _ = _make_feature(conn, project)
    env = json.loads(mcp_tools.cos_task_ready(conn, task_id=task_id))
    assert env["ok"] is True
    assert "ready" in env["data"]["labels"]


def test_ready_clean_when_dor_complete(project: Path, conn: sqlite3.Connection) -> None:
    task_id, file_path = _make_feature(conn, project)
    _fill_dor(file_path)
    env = json.loads(mcp_tools.cos_task_ready(conn, task_id=task_id))
    assert env["ok"] is True
    assert "ready" in env["data"]["labels"]
    assert not env["data"].get("dor"), f"complete task should surface no gaps: {env['data'].get('dor')}"


def test_unready_is_never_dor_gated(
    project: Path, conn: sqlite3.Connection, monkeypatch
) -> None:
    task_id, _ = _make_feature(conn, project)
    mcp_tools.cos_task_ready(conn, task_id=task_id)  # default warn → label lands
    monkeypatch.setenv("COS_READY_DOR", "strict")
    env = json.loads(mcp_tools.cos_task_ready(conn, task_id=task_id, ready=False))
    assert env["ok"] is True  # removing the label is never gated, even strict
    assert "ready" not in env["data"]["labels"]
