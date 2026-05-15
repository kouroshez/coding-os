from __future__ import annotations

import json
import os
import sqlite3
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "src" / "adapters" / "codex" / "hooks"

PRETOOL = HOOKS_DIR / "codex-pretool-dispatch.sh"
SESSIONSTART = HOOKS_DIR / "codex-sessionstart-dispatch.sh"
STOP = HOOKS_DIR / "codex-stop-dispatch.sh"


def _invoke(hook: Path, payload: dict, env: dict | None = None, cwd: Path | None = None) -> subprocess.CompletedProcess:
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    return subprocess.run(
        ["bash", str(hook)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=20,
        env=full_env,
        cwd=str(cwd) if cwd else None,
    )


def test_codex_pretool_dispatch_allows_safe_bash(tmp_path: Path) -> None:
    state = tmp_path / ".coding-os"
    state.mkdir()
    (state / "session-id").write_text("ses-safe\n")
    result = _invoke(
        PRETOOL,
        {"tool_name": "Bash", "tool_input": {"command": "ls -la"}},
        env={"COS_STATE_DIR": str(state)},
        cwd=tmp_path,
    )
    assert result.returncode == 0
    assert result.stderr == ""


def test_codex_pretool_dispatch_propagates_delegate_block(tmp_path: Path) -> None:
    state = tmp_path / ".coding-os"
    state.mkdir()
    (state / "session-id").write_text("ses-block\n")
    result = _invoke(
        PRETOOL,
        {"tool_name": "Bash", "tool_input": {"command": "git reset --hard HEAD~1"}},
        env={"COS_STATE_DIR": str(state)},
        cwd=tmp_path,
    )
    assert result.returncode == 2
    assert "reset --hard" in result.stderr


def test_codex_sessionstart_dispatch_creates_session_id(tmp_path: Path) -> None:
    """session-id now lives in the agent-private dir (COS_AGENT_DIR) so
    Claude and Codex never write to the same file. See
    docs/engineering/state-files.md."""
    state = tmp_path / ".coding-os"
    state.mkdir()
    # Pin COS_AGENT so the test runner's env doesn't flip detection.
    result = _invoke(
        SESSIONSTART,
        {"source": "startup"},
        env={
            "COS_STATE_DIR": str(state),
            "COS_AGENT": "codex",
            "CODEX_HOME": str(tmp_path / "home"),
        },
        cwd=tmp_path,
    )
    assert result.returncode == 0
    session_file = state / "codex" / "session-id"
    assert session_file.exists()
    # Session-id is agent-prefixed so downstream log lines are self-describing.
    assert session_file.read_text().strip().startswith("ses-codex-")


def test_codex_stop_dispatch_returns_valid_json(tmp_path: Path) -> None:
    state = tmp_path / ".coding-os"
    state.mkdir()
    (state / "session-id").write_text("ses-stop\n")
    db = state / "coding-os.db"
    conn = sqlite3.connect(str(db))
    conn.execute(
        "CREATE TABLE observations (id INTEGER PRIMARY KEY, session_id TEXT, body TEXT)"
    )
    conn.commit()
    conn.close()

    result = _invoke(
        STOP,
        {"hook_event_name": "Stop"},
        env={"COS_STATE_DIR": str(state), "COS_DB_PATH": str(db)},
        cwd=tmp_path,
    )
    assert result.returncode == 0
    assert json.loads(result.stdout) == {}
