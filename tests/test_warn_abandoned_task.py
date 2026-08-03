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


def test_silent_when_sibling_panel_binds_task(tmp_path: Path) -> None:
    """A task bound in a LIVE sibling panel is actively driven there —
    warning this (idle) panel about it invited the phantom NULL-reason
    icebox parks."""
    db = tmp_path / "coding-os.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE tasks (task_id TEXT, status TEXT, agent_session TEXT)")
    conn.execute("INSERT INTO tasks VALUES ('TASK-99', 'in_progress', 'ses-claude-test')")
    conn.commit()
    conn.close()
    panel = tmp_path / "panels" / "wa-panel"
    panel.mkdir(parents=True)
    (panel / "session-id").write_text("ses-claude-test", encoding="utf-8")
    sib = tmp_path / "panels" / "wa-sibling"
    sib.mkdir(parents=True)
    (sib / ".task-current").write_text("ses-other-session TASK-99", encoding="utf-8")
    (sib / "heartbeat").write_text("1\n", encoding="utf-8")

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


def test_rearms_on_state_change(tmp_path: Path) -> None:
    """Debounce keys on (session, open-set): a task progressing
    in_progress→testing changes the signature, so the nudge re-fires —
    catching the '85%-done then stopped' abandonment the once-per-session
    debounce went silent on."""
    db = tmp_path / "coding-os.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE tasks (task_id TEXT, status TEXT, agent_session TEXT)")
    conn.execute("INSERT INTO tasks VALUES ('TASK-99', 'in_progress', 'ses-claude-test')")
    conn.commit()
    conn.close()
    panel = tmp_path / "panels" / "wa-panel"
    panel.mkdir(parents=True)
    (panel / "session-id").write_text("ses-claude-test", encoding="utf-8")
    env = {"COS_DB_PATH": str(db), "COS_AGENT_DIR": str(tmp_path), "COS_PANEL_ID": "wa-panel"}

    assert _run(env).stdout.strip() != b""  # first warning (in_progress)
    assert _run(env).stdout.strip() == b""  # unchanged set → debounced

    conn = sqlite3.connect(db)
    conn.execute("UPDATE tasks SET status='testing' WHERE task_id='TASK-99'")
    conn.commit()
    conn.close()

    rearmed = _run(env)  # open-set signature changed → re-warn
    assert rearmed.stdout.strip() != b""
    assert "TASK-99" in json.loads(rearmed.stdout)["hookSpecificOutput"]["additionalContext"]


def _run_created_icebox(
    tmp_path: Path, labels_json: str | None
) -> subprocess.CompletedProcess[bytes]:
    # One icebox card CREATED by ses-claude-test — attributed via the
    # task_status_history 'created' row while tasks.agent_session is left NULL,
    # the exact parked-lane blind spot the create-then-park clause closes.
    db = tmp_path / "coding-os.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE tasks (task_id TEXT, status TEXT, agent_session TEXT, labels_json TEXT)"
    )
    conn.execute(
        "CREATE TABLE task_status_history "
        "(task_id TEXT, old_status TEXT, new_status TEXT, agent_session TEXT, reason TEXT, transitioned_at INTEGER)"
    )
    conn.execute("INSERT INTO tasks VALUES ('TASK-77', 'icebox', NULL, ?)", (labels_json,))
    conn.execute(
        "INSERT INTO task_status_history VALUES ('TASK-77', '', 'icebox', 'ses-claude-test', 'created', 1)"
    )
    conn.commit()
    conn.close()
    panel = tmp_path / "panels" / "wa-panel"
    panel.mkdir(parents=True)
    (panel / "session-id").write_text("ses-claude-test", encoding="utf-8")
    return _run(
        {"COS_DB_PATH": str(db), "COS_AGENT_DIR": str(tmp_path), "COS_PANEL_ID": "wa-panel"}
    )


def test_warns_on_created_then_parked_icebox(tmp_path: Path) -> None:
    """A card the session created and left un-ready in icebox is surfaced even
    though tasks.agent_session is NULL — attributed via the 'created' history row."""
    result = _run_created_icebox(tmp_path, None)
    assert result.returncode == 0
    ctx = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
    assert "TASK-77" in ctx
    assert "un-ready" in ctx


def test_ready_labeled_created_icebox_is_exempt(tmp_path: Path) -> None:
    """A 'ready' icebox card is a deliberate pull-queue — not create-then-park."""
    result = _run_created_icebox(tmp_path, '["ready"]')
    assert result.returncode == 0
    assert result.stdout.strip() == b""


def test_parked_labeled_created_icebox_is_exempt(tmp_path: Path) -> None:
    """A 'parked' label records deliberate long-term backlog — exempt from the nudge."""
    result = _run_created_icebox(tmp_path, '["parked"]')
    assert result.returncode == 0
    assert result.stdout.strip() == b""
