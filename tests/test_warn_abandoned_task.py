"""TASK-010 Group B — warn-abandoned-task.sh Stop hook smoke tests."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "src" / "core" / "hooks" / "warn-abandoned-task.sh"


def _run(env_extra: dict[str, str]) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["bash", str(HOOK)],
        input=b"{}",
        capture_output=True,
        env={**os.environ, **env_extra},
        timeout=10,
    )


def test_failopen_when_no_db(tmp_path: Path) -> None:
    result = _run({"COS_DB_PATH": str(tmp_path / "missing.db")})
    assert result.returncode == 0
    assert result.stdout.strip() == b""


def test_warns_on_stuck_task(tmp_path: Path) -> None:
    db = tmp_path / "coding-os.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE tasks (task_id TEXT, status TEXT, agent_session TEXT)")
    conn.execute("INSERT INTO tasks VALUES ('TASK-99', 'in_progress', 'ses-claude-test')")
    conn.commit()
    conn.close()
    # session-id is panel-scoped — the hook matches the
    # current panel session against tasks.agent_session.
    panel = tmp_path / "panels" / "wa-panel"
    panel.mkdir(parents=True)
    (panel / "session-id").write_text("ses-claude-test", encoding="utf-8")

    result = _run(
        {"COS_DB_PATH": str(db), "COS_AGENT_DIR": str(tmp_path), "COS_PANEL_ID": "wa-panel"}
    )
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert "TASK-99" in payload["hookSpecificOutput"]["additionalContext"]


def test_silent_when_no_stuck_task(tmp_path: Path) -> None:
    db = tmp_path / "coding-os.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE tasks (task_id TEXT, status TEXT, agent_session TEXT)")
    conn.execute("INSERT INTO tasks VALUES ('TASK-1', 'complete', 'ses-claude-test')")
    conn.commit()
    conn.close()
    # session-id is panel-scoped — the hook matches the
    # current panel session against tasks.agent_session.
    panel = tmp_path / "panels" / "wa-panel"
    panel.mkdir(parents=True)
    (panel / "session-id").write_text("ses-claude-test", encoding="utf-8")

    result = _run(
        {"COS_DB_PATH": str(db), "COS_AGENT_DIR": str(tmp_path), "COS_PANEL_ID": "wa-panel"}
    )
    assert result.returncode == 0
    assert result.stdout.strip() == b""


def test_debounced_after_first_warning(tmp_path: Path) -> None:
    db = tmp_path / "coding-os.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE tasks (task_id TEXT, status TEXT, agent_session TEXT)")
    conn.execute("INSERT INTO tasks VALUES ('TASK-99', 'in_progress', 'ses-claude-test')")
    conn.commit()
    conn.close()
    # session-id is panel-scoped — the hook matches the
    # current panel session against tasks.agent_session.
    panel = tmp_path / "panels" / "wa-panel"
    panel.mkdir(parents=True)
    (panel / "session-id").write_text("ses-claude-test", encoding="utf-8")

    env = {"COS_DB_PATH": str(db), "COS_AGENT_DIR": str(tmp_path), "COS_PANEL_ID": "wa-panel"}
    first = _run(env)
    second = _run(env)
    assert first.stdout.strip() != b""
    assert second.stdout.strip() == b""
