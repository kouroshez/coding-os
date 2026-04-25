"""Tests for `cos task-create` enriched output (Phase L.10 / TASK-110+111).

Covers:
- next_steps payload mirrors the kind's DoR rules.
- Body sections rendered match the kind (bug→Repro Steps, security→Threat Model,
  chore→Outcome only, etc.).
- Outcome placeholder is kind-flavoured.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
import yaml

from core.board_os import mcp_tools
from core.thinking_os import db


@pytest.fixture
def project(tmp_path: Path, monkeypatch) -> Path:
    (tmp_path / ".coding-os").mkdir()
    (tmp_path / ".coding-os" / "scrumban-config.yaml").write_text(
        yaml.safe_dump(
            {
                "swimlanes": [{"id": "core", "label": "Core", "color": "#3b82f6"}],
                "wip_limits": {"in_progress": 2, "testing": 3, "emergency": 2},
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
    return db.init_db(tmp_path / "thinking-os.db")


def _create(conn, kind: str) -> dict:
    env = json.loads(
        mcp_tools.cos_task_create(
            conn, title=f"smoke {kind}", swimlane="core", kind=kind,
        )
    )
    assert env["ok"] is True
    return env


def _body(project: Path, env: dict) -> str:
    return (project / env["data"]["file_path"]).read_text(encoding="utf-8")


# ────────────────────────────────────────────────────────────────────
# next_steps shape
# ────────────────────────────────────────────────────────────────────


def test_next_steps_present_for_every_kind(project: Path, conn: sqlite3.Connection) -> None:
    for kind in ("feature", "bug", "chore", "spike", "docs", "refactor", "test", "security"):
        env = _create(conn, kind)
        ns = env["data"]["next_steps"]
        assert ns["kind"] == kind
        assert "required_for_in_progress" in ns
        assert ns["command_after_fill"] == "cos task-start <TASK-ID>"
        assert ns["preview_command"] == "cos task-validate <TASK-ID>"


def test_next_steps_chore_lists_only_outcome(
    project: Path, conn: sqlite3.Connection,
) -> None:
    env = _create(conn, "chore")
    sections = [s["section"] for s in env["data"]["next_steps"]["required_for_in_progress"]]
    assert sections == ["Outcome"]


def test_next_steps_bug_includes_repro_steps(
    project: Path, conn: sqlite3.Connection,
) -> None:
    env = _create(conn, "bug")
    sections = [s["section"] for s in env["data"]["next_steps"]["required_for_in_progress"]]
    assert "Repro Steps" in sections
    assert "Acceptance" in sections


def test_next_steps_security_includes_threat_model(
    project: Path, conn: sqlite3.Connection,
) -> None:
    env = _create(conn, "security")
    sections = [s["section"] for s in env["data"]["next_steps"]["required_for_in_progress"]]
    assert "Threat Model" in sections
    assert "Acceptance" in sections


def test_next_steps_includes_min_chars_when_set(
    project: Path, conn: sqlite3.Connection,
) -> None:
    env = _create(conn, "feature")
    outcome_spec = next(
        s for s in env["data"]["next_steps"]["required_for_in_progress"]
        if s["section"] == "Outcome"
    )
    assert outcome_spec["min_chars"] >= 20
    assert "(fill in" in outcome_spec["forbid_substrings"]


# ────────────────────────────────────────────────────────────────────
# Body shape — sections rendered match kind
# ────────────────────────────────────────────────────────────────────


def test_chore_body_omits_acceptance_and_read_first(
    project: Path, conn: sqlite3.Connection,
) -> None:
    env = _create(conn, "chore")
    body = _body(project, env)
    assert "## Acceptance" not in body
    assert "## Read First" not in body
    assert "## Work Log" in body
    assert "**Outcome" in body


def test_bug_body_includes_repro_steps(
    project: Path, conn: sqlite3.Connection,
) -> None:
    env = _create(conn, "bug")
    body = _body(project, env)
    assert "## Repro Steps" in body
    assert "## Acceptance" in body
    assert "## Read First" in body


def test_security_body_includes_threat_model(
    project: Path, conn: sqlite3.Connection,
) -> None:
    env = _create(conn, "security")
    body = _body(project, env)
    assert "## Threat Model" in body
    assert "## Acceptance" in body


def test_spike_body_only_outcome(
    project: Path, conn: sqlite3.Connection,
) -> None:
    env = _create(conn, "spike")
    body = _body(project, env)
    assert "## Acceptance" not in body
    assert "## Read First" not in body


def test_feature_body_full_template(
    project: Path, conn: sqlite3.Connection,
) -> None:
    env = _create(conn, "feature")
    body = _body(project, env)
    assert "## Read First" in body
    assert "## Acceptance" in body


# ────────────────────────────────────────────────────────────────────
# Outcome placeholder text
# ────────────────────────────────────────────────────────────────────


def test_outcome_placeholder_is_kind_flavoured(
    project: Path, conn: sqlite3.Connection,
) -> None:
    env_bug = _create(conn, "bug")
    env_chore = _create(conn, "chore")
    body_bug = _body(project, env_bug)
    body_chore = _body(project, env_chore)
    # bug + chore use distinct example phrasings
    assert "double-charging" in body_bug or "Stop" in body_bug
    assert "Bump dependency" in body_chore or "security patch" in body_chore


def test_explicit_outcome_overrides_placeholder(
    project: Path, conn: sqlite3.Connection,
) -> None:
    env = json.loads(
        mcp_tools.cos_task_create(
            conn,
            title="explicit",
            swimlane="core",
            kind="chore",
            outcome="My very specific outcome line.",
        )
    )
    body = _body(project, env)
    assert "My very specific outcome line." in body
    assert "(fill in" not in body
