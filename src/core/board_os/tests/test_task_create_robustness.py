"""board_os robustness guards (TASK-400).

Covers:
  - depends_on format validation at create time (malformed ids never reach
    the cycle detector / dependents junction)
  - honest DoR echo: dor.ready is False whenever block-severity gaps exist,
    even when the ready label was requested
  - one-shot bug create: acceptance= + repro= fill the kind's DoR sections
    in the same call
  - parser drops malformed depends_on/blocked_by ids with a parse warning
  - sync_one rejects duplicate-frontmatter files loudly
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
import yaml

from core.board_os import mcp_tools
from core.board_os.parser import parse_task
from core.board_os.sync import sync_all
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
    c = db.init_db(tmp_path / "coding-os.db")
    yield c
    c.close()


class TestDependsOnValidation:
    def test_malformed_depends_on_fails_validation(self, conn, project) -> None:
        env = json.loads(
            mcp_tools.cos_task_create(
                conn,
                title="Bad deps",
                swimlane="core",
                kind="feature",
                depends_on=["TASK1", "TASK-002"],
            )
        )
        assert env["ok"] is False
        assert env["error"]["category"] == "validation"
        assert "TASK1" in env["error"]["message"]

    def test_wellformed_depends_on_passes(self, conn, project) -> None:
        env = json.loads(
            mcp_tools.cos_task_create(
                conn,
                title="Good deps",
                swimlane="core",
                kind="feature",
                depends_on=["TASK-002", "TASK-NS-7"],
            )
        )
        assert env["ok"] is True


class TestHonestDor:
    def test_ready_false_when_block_gaps_exist(self, conn, project) -> None:
        env = json.loads(
            mcp_tools.cos_task_create(
                conn,
                title="Skeleton bug",
                swimlane="core",
                kind="bug",
                outcome="Stop the crash in the allocator under lock contention.",
                read_first=["src/core/board_os/mcp_tools.py"],
                ready=True,
            )
        )
        dor = env["data"]["dor"]
        assert any(g.get("severity") == "block" for g in dor["gaps"])
        assert dor["ready"] is False
        assert dor["label_ready"] is True

    def test_one_shot_bug_create_satisfies_dor(self, conn, project) -> None:
        env = json.loads(
            mcp_tools.cos_task_create(
                conn,
                title="Full bug",
                swimlane="core",
                kind="bug",
                outcome="Stop the crash in the allocator under lock contention.",
                read_first=["src/core/board_os/mcp_tools.py"],
                acceptance=(
                    "- **Given** a locked DB, **When** create runs, "
                    "**Then** it returns fail('unavailable')."
                ),
                repro=(
                    "1. Hold the write lock from a second connection.\n"
                    "2. Call cos_task_create.\n"
                    "Expected: fail envelope.\n"
                    "Actual: unhandled OperationalError."
                ),
                ready=True,
            )
        )
        dor = env["data"]["dor"]
        assert dor["gaps"] == []
        assert dor["ready"] is True


class TestParserTaskIdNormalization:
    def test_malformed_ids_dropped_with_warning(self) -> None:
        content = (
            "---\n"
            "id: TASK-010\n"
            'title: "X"\n'
            "swimlane: core\n"
            "kind: feature\n"
            "status: icebox\n"
            "priority: P2\n"
            "appetite: 1d\n"
            "depends_on: [TASK-001, garbage, TASK-9x]\n"
            "blocked_by: [TASK2]\n"
            "---\n"
            "# TASK-010: X\n\n**Outcome (one sentence):** Y.\n"
        )
        parsed = parse_task(content)
        assert parsed.depends_on == ("TASK-001",)
        assert parsed.blocked_by == ()
        joined = " ".join(parsed.parse_warnings)
        assert "garbage" in joined and "TASK2" in joined


class TestDuplicateFrontmatterRejection:
    def test_sync_rejects_double_frontmatter(self, conn, project, caplog) -> None:
        card = (
            "---\n"
            "id: TASK-020\n"
            'title: "Dup"\n'
            "swimlane: core\n"
            "kind: feature\n"
            "status: icebox\n"
            "priority: P2\n"
            "appetite: 1d\n"
            "---\n"
            "# TASK-020: Dup\n\n"
            "---\n"
            "id: TASK-020\n"
            "status: complete\n"
            "---\n"
        )
        (project / "docs" / "tasks" / "TASK-020-dup.md").write_text(card, encoding="utf-8")
        with caplog.at_level("WARNING"):
            stats = sync_all(conn, project_root=project)
        assert stats["parse_errors"] == 1
        assert any("duplicate frontmatter" in r.message for r in caplog.records)
