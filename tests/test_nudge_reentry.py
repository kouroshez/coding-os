"""TASK-666 — nudge-reentry.sh UserPromptSubmit hook smoke tests."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "src" / "core" / "hooks" / "nudge-reentry.sh"


def _make_db(tmp_path: Path, task_id: str, status: str, session: str) -> Path:
    db = tmp_path / "coding-os.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE tasks (task_id TEXT, status TEXT, agent_session TEXT)")
    conn.execute("INSERT INTO tasks VALUES (?, ?, ?)", (task_id, status, session))
    conn.commit()
    conn.close()
    return db


def _panel(tmp_path: Path, session: str, task_current: str | None = None) -> None:
    panel = tmp_path / "panels" / "nr-panel"
    panel.mkdir(parents=True, exist_ok=True)
    (panel / "session-id").write_text(session, encoding="utf-8")
    if task_current is not None:
        (panel / ".task-current").write_text(task_current, encoding="utf-8")


def _run(tmp_path: Path, db: Path) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["bash", str(HOOK)],
        input=b"{}",
        capture_output=True,
        env={
            **os.environ,
            "COS_DB_PATH": str(db),
            "COS_AGENT_DIR": str(tmp_path),
            "COS_PANEL_ID": "nr-panel",
        },
        timeout=10,
    )


def test_failopen_when_no_db(tmp_path: Path) -> None:
    result = subprocess.run(
        ["bash", str(HOOK)],
        input=b"{}",
        capture_output=True,
        env={**os.environ, "COS_DB_PATH": str(tmp_path / "missing.db")},
        timeout=10,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == b""


def test_nudges_when_in_progress_unbound(tmp_path: Path) -> None:
    db = _make_db(tmp_path, "TASK-99", "in_progress", "ses-claude-test")
    _panel(tmp_path, "ses-claude-test")  # no .task-current → unbound
    result = _run(tmp_path, db)
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"
    assert "TASK-99" in payload["hookSpecificOutput"]["additionalContext"]


def test_silent_when_bound(tmp_path: Path) -> None:
    db = _make_db(tmp_path, "TASK-99", "in_progress", "ses-claude-test")
    _panel(tmp_path, "ses-claude-test", task_current="TASK-99")
    result = _run(tmp_path, db)
    assert result.returncode == 0
    assert result.stdout.strip() == b""


def test_nudges_on_mismatch(tmp_path: Path) -> None:
    db = _make_db(tmp_path, "TASK-99", "in_progress", "ses-claude-test")
    _panel(tmp_path, "ses-claude-test", task_current="TASK-42")  # bound to a different task
    result = _run(tmp_path, db)
    assert result.returncode == 0
    assert "TASK-99" in json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]


def test_silent_when_no_in_progress(tmp_path: Path) -> None:
    db = _make_db(tmp_path, "TASK-1", "complete", "ses-claude-test")
    _panel(tmp_path, "ses-claude-test")
    result = _run(tmp_path, db)
    assert result.returncode == 0
    assert result.stdout.strip() == b""


def test_debounced_after_first_nudge(tmp_path: Path) -> None:
    db = _make_db(tmp_path, "TASK-99", "in_progress", "ses-claude-test")
    _panel(tmp_path, "ses-claude-test")
    first = _run(tmp_path, db)
    second = _run(tmp_path, db)
    assert first.stdout.strip() != b""
    assert second.stdout.strip() == b""


def _sibling(tmp_path: Path, panel_id: str, task_current: str, heartbeat_age_s: int = 0) -> None:
    sib = tmp_path / "panels" / panel_id
    sib.mkdir(parents=True, exist_ok=True)
    # Production shape: write-state.sh prefixes the session id.
    (sib / ".task-current").write_text(f"ses-other-session {task_current}", encoding="utf-8")
    hb = sib / "heartbeat"
    hb.write_text("1\n", encoding="utf-8")
    if heartbeat_age_s:
        old = hb.stat().st_mtime - heartbeat_age_s
        os.utime(hb, (old, old))


def test_silent_when_sibling_panel_binds_task(tmp_path: Path) -> None:
    """A task bound in a LIVE sibling panel is actively driven there —
    nudging this (idle) panel about it invited the phantom NULL-reason
    icebox parks."""
    db = _make_db(tmp_path, "TASK-99", "in_progress", "ses-claude-test")
    _panel(tmp_path, "ses-claude-test")  # this panel: unbound
    _sibling(tmp_path, "sibling-panel", "TASK-99")  # fresh heartbeat
    result = _run(tmp_path, db)
    assert result.returncode == 0
    assert result.stdout.strip() == b""


def test_nudges_when_sibling_binding_is_stale(tmp_path: Path) -> None:
    db = _make_db(tmp_path, "TASK-99", "in_progress", "ses-claude-test")
    _panel(tmp_path, "ses-claude-test")
    _sibling(tmp_path, "sibling-panel", "TASK-99", heartbeat_age_s=7200)
    result = _run(tmp_path, db)
    assert result.returncode == 0
    assert "TASK-99" in json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]


def test_silent_when_bound_with_session_prefix(tmp_path: Path) -> None:
    """Production .task-current carries a session-id prefix; the bound-check
    must parse the task token, not the raw first 32 bytes."""
    db = _make_db(tmp_path, "TASK-99", "in_progress", "ses-claude-test")
    _panel(tmp_path, "ses-claude-test", task_current="ses-claude-20260527-151803-0b9f TASK-99")
    result = _run(tmp_path, db)
    assert result.returncode == 0
    assert result.stdout.strip() == b""
