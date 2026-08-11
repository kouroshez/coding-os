"""Tests for Phase F hooks (MCP visibility + workflow integrity).

Four new hooks address the invisible failure modes that cost us most of
today's session (MCP down, capture silent-failing, zero observations):

  warn-mcp-down.sh          — SessionStart banner when MCP is dead
  check-capture-worked.sh   — Stop-time recap if observations missing
  enforce-memory-check.sh   — PreToolUse require cos_search in Orient
  remind-learn-validate.sh  — PostToolUse Bash nudge after task-done

Plus C15 regression tests — verify the doctor check catches the exact
form of broken .mcp.json that bit us in real life.
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.slow  # dominated by cos-init / subprocess tests

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "src" / "core" / "hooks"

WARN_MCP_DOWN = HOOKS_DIR / "warn-mcp-down.sh"
CHECK_CAPTURE_WORKED = HOOKS_DIR / "check-capture-worked.sh"
ENFORCE_MEMORY_CHECK = HOOKS_DIR / "enforce-memory-check.sh"
REMIND_LEARN_VALIDATE = HOOKS_DIR / "remind-learn-validate.sh"
SESSION_CONTEXT = HOOKS_DIR / "session-context.sh"
BLOCK_DANGEROUS_COMMANDS = HOOKS_DIR / "block-dangerous-commands.sh"


def _invoke(hook: Path, payload: dict, env: dict | None = None) -> subprocess.CompletedProcess:
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
    )


# ============================================================
# session-context.sh
# ============================================================


class TestCheckCaptureWorked:
    PANEL_ID = "cap-panel"

    def _setup(self, tmp_path: Path, session_id: str = "ses-claude-test-1") -> Path:
        state = tmp_path / ".coding-os"
        state.mkdir()
        # session-id is panel-scoped — the hook reads the
        # current session from $COS_PANEL_DIR to match hooks.log entries.
        panel_dir = state / "claude" / "panels" / self.PANEL_ID
        panel_dir.mkdir(parents=True)
        (panel_dir / "session-id").write_text(session_id + "\n")
        return state

    def _env_for(self, state: Path) -> dict:
        return {
            "COS_STATE_DIR": str(state),
            "COS_AGENT_DIR": str(state / "claude"),
            "COS_AGENT": "claude",
            "COS_PANEL_ID": self.PANEL_ID,
        }

    def _init_db(self, db_path: Path) -> None:
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "CREATE TABLE observations (id INTEGER PRIMARY KEY, session_id TEXT, body TEXT)"
        )
        conn.commit()
        conn.close()

    def test_silent_when_observations_present(self, tmp_path: Path) -> None:
        state = self._setup(tmp_path)
        db = state / "coding-os.db"
        self._init_db(db)
        conn = sqlite3.connect(str(db))
        conn.execute(
            "INSERT INTO observations (session_id, body) VALUES (?, ?)",
            ("ses-claude-test-1", "x"),
        )
        conn.commit()
        conn.close()
        env = {**self._env_for(state), "COS_DB_PATH": str(db)}
        r = _invoke(CHECK_CAPTURE_WORKED, {}, env=env)
        assert r.returncode == 0
        assert r.stdout == ""
        assert r.stderr == ""

    def test_warns_when_zero_observations(self, tmp_path: Path) -> None:
        state = self._setup(tmp_path)
        db = state / "coding-os.db"
        self._init_db(db)
        # A read-only session (no Write/Edit) is expected to capture 0 obs and
        # is intentionally silent. Simulate a session that DID edit code so the
        # zero-observation drift warning actually fires: capture-observation
        # logs `[capture-observation] [fire] ... session=<sid> ... tool=Write`.
        (state / ".hooks.log").write_text(
            "[2026-05-21T00:00:00] [capture-observation] [fire] "
            "agent=claude session=ses-claude-test-1 task=none tool=Write\n"
        )
        env = {**self._env_for(state), "COS_DB_PATH": str(db)}
        r = _invoke(CHECK_CAPTURE_WORKED, {}, env=env)
        assert r.returncode == 0
        assert "0 observations recorded" in r.stderr

    def test_shows_error_log_if_present(self, tmp_path: Path) -> None:
        state = self._setup(tmp_path)
        (state / ".capture-errors.log").write_text(
            "Traceback line 1\nsqlite3.OperationalError: bad\n"
        )
        db = state / "coding-os.db"
        self._init_db(db)
        env = {**self._env_for(state), "COS_DB_PATH": str(db)}
        r = _invoke(CHECK_CAPTURE_WORKED, {}, env=env)
        assert "capture-observation failed" in r.stderr
        assert "sqlite3.OperationalError" in r.stderr

    def test_truncates_error_log(self, tmp_path: Path) -> None:
        state = self._setup(tmp_path)
        err_log = state / ".capture-errors.log"
        err_log.write_text("some error\n")
        db = state / "coding-os.db"
        self._init_db(db)
        env = {**self._env_for(state), "COS_DB_PATH": str(db)}
        _invoke(CHECK_CAPTURE_WORKED, {}, env=env)
        assert err_log.exists()
        assert err_log.read_text() == ""


class TestEnforceMemoryCheck:
    PANEL_ID = "mc-panel"

    def _setup(self, tmp_path: Path) -> Path:
        """Return the shared state root. Per-panel markers (.memory-check,
        .thinking_os-gate, .task-current, session-id) live in
        state/claude/panels/<panel-id>/ since TASK-035; the hook reads them
        from $COS_PANEL_DIR. Use `self._panel(state)` to write them."""
        state = tmp_path / ".coding-os"
        state.mkdir()
        panel_dir = state / "claude" / "panels" / self.PANEL_ID
        panel_dir.mkdir(parents=True)
        (panel_dir / "session-id").write_text("ses-claude-mc\n")
        return state

    def _panel(self, state: Path) -> Path:
        return state / "claude" / "panels" / self.PANEL_ID

    def _env(self, state: Path) -> dict:
        return {
            "COS_STATE_DIR": str(state),
            "COS_AGENT_DIR": str(state / "claude"),
            "COS_AGENT": "claude",
            "COS_PANEL_ID": self.PANEL_ID,
        }

    def test_blocks_when_no_marker(self, tmp_path: Path) -> None:
        state = self._setup(tmp_path)
        env = self._env(state)
        p = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(tmp_path / "src" / "cli" / "main.py"),
                "content": "x",
            },
        }
        r = _invoke(ENFORCE_MEMORY_CHECK, p, env=env)
        assert r.returncode == 2
        assert "Memory Check" in r.stderr

    def test_allows_when_marker_present(self, tmp_path: Path) -> None:
        state = self._setup(tmp_path)
        (self._panel(state) / ".memory-check").write_text("ses-claude-mc cos_search:auth\n")
        env = self._env(state)
        p = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(tmp_path / "src" / "cli" / "main.py"),
                "content": "x",
            },
        }
        r = _invoke(ENFORCE_MEMORY_CHECK, p, env=env)
        assert r.returncode == 0

    def test_exempt_on_clear_1(self, tmp_path: Path) -> None:
        state = self._setup(tmp_path)
        (self._panel(state) / ".thinking_os-gate").write_text("ses-claude-mc CLEAR 1\n")
        env = self._env(state)
        p = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(tmp_path / "src" / "cli" / "main.py"),
                "content": "x",
            },
        }
        r = _invoke(ENFORCE_MEMORY_CHECK, p, env=env)
        assert r.returncode == 0

    def test_exempt_on_exploratory_task(self, tmp_path: Path) -> None:
        state = self._setup(tmp_path)
        (self._panel(state) / ".task-current").write_text("ses-claude-mc exploratory-refactor\n")
        env = self._env(state)
        p = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(tmp_path / "src" / "cli" / "main.py"),
                "content": "x",
            },
        }
        r = _invoke(ENFORCE_MEMORY_CHECK, p, env=env)
        assert r.returncode == 0

    def test_exempt_on_non_code(self, tmp_path: Path) -> None:
        state = self._setup(tmp_path)
        env = self._env(state)
        p = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(tmp_path / "docs" / "x.md"),
                "content": "x",
            },
        }
        r = _invoke(ENFORCE_MEMORY_CHECK, p, env=env)
        assert r.returncode == 0

    def test_exempt_on_test_file(self, tmp_path: Path) -> None:
        state = self._setup(tmp_path)
        env = self._env(state)
        p = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(tmp_path / "tests" / "test_foo.py"),
                "content": "x",
            },
        }
        r = _invoke(ENFORCE_MEMORY_CHECK, p, env=env)
        assert r.returncode == 0

    def test_override_one_shot(self, tmp_path: Path) -> None:
        state = self._setup(tmp_path)
        override_file = state / "claude" / ".memory-check-override"
        override_file.write_text("")
        env = self._env(state)
        p = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(tmp_path / "src" / "cli" / "main.py"),
                "content": "x",
            },
        }
        r = _invoke(ENFORCE_MEMORY_CHECK, p, env=env)
        assert r.returncode == 0
        assert not override_file.exists()


class TestRemindLearnValidate:
    def _setup(self, tmp_path: Path) -> tuple[Path, Path, dict]:
        """Return (state_root, agent_dir, env). Suggestions live in the
        agent-private dir per the state-scope split."""
        state = tmp_path / ".coding-os"
        state.mkdir()
        agent_dir = state / "claude"
        agent_dir.mkdir()
        env = {
            "COS_STATE_DIR": str(state),
            "COS_AGENT_DIR": str(agent_dir),
            "COS_AGENT": "claude",
        }
        return state, agent_dir, env

    def test_fires_on_make_task_done(self, tmp_path: Path) -> None:
        _, agent_dir, env = self._setup(tmp_path)
        (agent_dir / ".learn-suggestions").write_text("42\tPattern A\n43\tPattern B\n")
        p = {
            "tool_name": "Bash",
            "tool_input": {
                "command": "make task-done TASK=1 TYPE=feat MSG=x",
            },
        }
        r = _invoke(REMIND_LEARN_VALIDATE, p, env=env)
        assert r.returncode == 0
        assert "cos_learn_validate" in r.stdout
        assert "42" in r.stdout

    def test_silent_on_unrelated_bash(self, tmp_path: Path) -> None:
        _, agent_dir, env = self._setup(tmp_path)
        (agent_dir / ".learn-suggestions").write_text("42\tPattern A\n")
        p = {"tool_name": "Bash", "tool_input": {"command": "ls -la"}}
        r = _invoke(REMIND_LEARN_VALIDATE, p, env=env)
        assert r.returncode == 0
        assert r.stdout == ""

    def test_silent_when_no_suggestions_file(self, tmp_path: Path) -> None:
        _, _, env = self._setup(tmp_path)
        p = {
            "tool_name": "Bash",
            "tool_input": {
                "command": "make task-done TASK=1",
            },
        }
        r = _invoke(REMIND_LEARN_VALIDATE, p, env=env)
        assert r.returncode == 0
        assert r.stdout == ""

    def test_clears_suggestions_after_reminder(self, tmp_path: Path) -> None:
        _, agent_dir, env = self._setup(tmp_path)
        sugg = agent_dir / ".learn-suggestions"
        sugg.write_text("42\tPattern A\n")
        p = {
            "tool_name": "Bash",
            "tool_input": {
                "command": "make task-done TASK=1",
            },
        }
        _invoke(REMIND_LEARN_VALIDATE, p, env=env)
        assert sugg.read_text() == ""
