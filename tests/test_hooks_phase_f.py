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


class TestSessionContext:
    def test_startup_clears_session_scoped_markers(self, tmp_path: Path) -> None:
        """State clear on startup targets THIS PANEL's private dir
        ($COS_PANEL_DIR), not the agent root. Per docs/engineering/
        state-files.md: agent-level dir is shared across panels of the
        same agent; cognitive markers live one level deeper in
        $COS_AGENT_DIR/panels/<panel-id>/. Pinning COS_PANEL_ID gives a
        deterministic panel-dir to assert against."""
        state = tmp_path / ".coding-os"
        state.mkdir()
        agent_dir = state / "codex"
        agent_dir.mkdir()
        panel_id = "test-startup-clear"
        panel_dir = agent_dir / "panels" / panel_id
        panel_dir.mkdir(parents=True)

        # Per-panel volatile markers — must be cleared by startup.
        PANEL_MARKERS = [
            ".thinking_os-gate",
            ".task-current",
            ".zoom-checkpoint",
            ".active-skill",
            ".doc-anchor",
            ".memory-check",
            ".learn-suggestions",
            ".doc-anchor-override",
            ".memory-check-override",
            ".uv-heredoc-override",
        ]
        for name in PANEL_MARKERS:
            (panel_dir / name).write_text("stale\n")
        # Shared error log lives at the root and is also cleared on startup.
        (state / ".capture-errors.log").write_text("stale\n")

        # Pin agent + panel explicitly so cos-env.sh heuristics (which
        # pick up CLAUDECODE / CODEX_* from the test runner's environment)
        # cannot flip the target dir.
        env = {
            "COS_STATE_DIR": str(state),
            "COS_AGENT": "codex",
            "COS_PANEL_ID": panel_id,
            "CODEX_HOME": str(tmp_path / "home"),
        }
        r = subprocess.run(
            ["bash", str(SESSION_CONTEXT)],
            input=json.dumps({"source": "startup"}),
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(tmp_path),
            env={**os.environ, **env},
        )
        assert r.returncode == 0
        for name in PANEL_MARKERS:
            assert not (panel_dir / name).exists(), f"panel marker {name} not cleared"
        assert not (state / ".capture-errors.log").exists()
        log_text = (state / ".hooks.log").read_text()
        assert "[session-context] [reset]" in log_text
        # Session-id ends up in the per-panel dir, format ses-<agent>-...
        session_id = (panel_dir / "session-id").read_text().strip()
        assert session_id.startswith("ses-codex-"), session_id

    def test_user_prompt_submit_does_not_rotate_session_or_clear_state(
        self, tmp_path: Path
    ) -> None:
        state = tmp_path / ".coding-os"
        state.mkdir()
        agent_dir = state / "codex"
        agent_dir.mkdir()
        (agent_dir / "session-id").write_text("ses-codex-existing\n")
        (agent_dir / ".task-current").write_text("TASK-123\n")

        env = {
            "COS_STATE_DIR": str(state),
            "COS_AGENT": "codex",
            "CODEX_HOME": str(tmp_path / "home"),
        }
        r = subprocess.run(
            ["bash", str(SESSION_CONTEXT)],
            input=json.dumps({"turn_id": "turn-1", "prompt": "continue working"}),
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(tmp_path),
            env={**os.environ, **env},
        )

        assert r.returncode == 0
        assert (agent_dir / "session-id").read_text().strip() == "ses-codex-existing"
        assert (agent_dir / ".task-current").exists()
        log_text = (state / ".hooks.log").read_text()
        assert "[session-context] [reset]" not in log_text


# ============================================================
# warn-mcp-down.sh
# ============================================================


class TestWarnMcpDown:
    def test_silent_when_no_mcp_json(self, tmp_path: Path) -> None:
        hook_dir = tmp_path / ".claude" / "hooks"
        hook_dir.mkdir(parents=True)
        (hook_dir / "warn-mcp-down.sh").symlink_to(WARN_MCP_DOWN)
        home = tmp_path / "home"
        home.mkdir()
        r = subprocess.run(
            ["bash", str(hook_dir / "warn-mcp-down.sh")],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(tmp_path),
            env={**os.environ, "HOME": str(home)},
        )
        assert r.returncode == 0
        assert r.stdout == ""
        assert r.stderr == ""

    def test_silent_when_no_coding_os_entry(self, tmp_path: Path) -> None:
        hook_dir = tmp_path / ".claude" / "hooks"
        hook_dir.mkdir(parents=True)
        (hook_dir / "warn-mcp-down.sh").symlink_to(WARN_MCP_DOWN)
        (tmp_path / ".mcp.json").write_text(
            json.dumps({"mcpServers": {"other-thing": {"command": "x"}}})
        )
        home = tmp_path / "home"
        home.mkdir()
        r = subprocess.run(
            ["bash", str(hook_dir / "warn-mcp-down.sh")],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(tmp_path),
            env={**os.environ, "HOME": str(home)},
        )
        assert r.returncode == 0
        assert "coding-os is DOWN" not in r.stderr

    def test_warns_when_command_not_found(self, tmp_path: Path) -> None:
        hook_dir = tmp_path / ".claude" / "hooks"
        hook_dir.mkdir(parents=True)
        (hook_dir / "warn-mcp-down.sh").symlink_to(WARN_MCP_DOWN)
        (tmp_path / ".mcp.json").write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "coding-os": {"command": "this-cmd-does-not-exist-xyz", "args": []}
                    }
                }
            )
        )
        r = subprocess.run(
            ["bash", str(hook_dir / "warn-mcp-down.sh")],
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert r.returncode == 0
        assert "DOWN" in r.stderr
        assert "MCP server is unreachable" in r.stdout

    def test_reads_codex_project_config_when_mcp_json_absent(self, tmp_path: Path) -> None:
        hook_dir = tmp_path / ".codex" / "hooks"
        hook_dir.mkdir(parents=True)
        (hook_dir / "warn-mcp-down.sh").symlink_to(WARN_MCP_DOWN)
        (tmp_path / ".codex" / "config.toml").write_text(
            "[mcp_servers.coding-os]\n"
            'command = "this-cmd-does-not-exist-xyz"\n'
            'args = ["server-start"]\n',
            encoding="utf-8",
        )
        r = subprocess.run(
            ["bash", str(hook_dir / "warn-mcp-down.sh")],
            capture_output=True,
            text=True,
            timeout=15,
            cwd=str(tmp_path),
        )
        assert r.returncode == 0
        assert "DOWN" in r.stderr
        assert "MCP server is unreachable" in r.stdout

    def test_prefers_codex_project_config_over_global(self, tmp_path: Path) -> None:
        hook_dir = tmp_path / ".codex" / "hooks"
        hook_dir.mkdir(parents=True)
        (hook_dir / "warn-mcp-down.sh").symlink_to(WARN_MCP_DOWN)
        (tmp_path / ".codex" / "config.toml").write_text(
            '[mcp_servers.coding-os]\ncommand = "project-cmd-does-not-exist-xyz"\n',
            encoding="utf-8",
        )
        home = tmp_path / "home"
        (home / ".codex").mkdir(parents=True)
        (home / ".codex" / "config.toml").write_text(
            "[mcp_servers.coding-os]\n"
            'command = "python3"\n'
            'args = ["-c", "import sys; sys.stdout.write(\'{\\\\\\"jsonrpc\\\\\\":\\\\\\"2.0\\\\\\",\\\\\\"result\\\\\\":{}}\')"]\n',
            encoding="utf-8",
        )
        r = subprocess.run(
            ["bash", str(hook_dir / "warn-mcp-down.sh")],
            capture_output=True,
            text=True,
            timeout=15,
            cwd=str(tmp_path),
            env={**os.environ, "HOME": str(home)},
        )
        assert r.returncode == 0
        assert "DOWN" in r.stderr


# ============================================================
# check-capture-worked.sh
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


# ============================================================
# enforce-memory-check.sh
# ============================================================


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


# ============================================================
# remind-learn-validate.sh
# ============================================================


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


# ============================================================
# Hook visibility regression
# ============================================================


class TestHookVisibility:
    def test_bash_guard_logs_fire_for_codex_sessions(self, tmp_path: Path) -> None:
        state = tmp_path / ".coding-os"
        state.mkdir()
        agent_dir = state / "codex"
        agent_dir.mkdir()
        (agent_dir / "session-id").write_text("ses-codex-log\n")
        # Pin COS_AGENT so the test runner's CLAUDECODE env var doesn't
        # flip detection back to claude.
        env = {
            "COS_STATE_DIR": str(state),
            "COS_AGENT_DIR": str(agent_dir),
            "COS_AGENT": "codex",
            "CODEX_HOME": str(tmp_path / "home"),
        }
        p = {"tool_name": "Bash", "tool_input": {"command": "ls -la"}}
        r = _invoke(BLOCK_DANGEROUS_COMMANDS, p, env=env)
        assert r.returncode == 0
        log_text = (state / ".hooks.log").read_text()
        assert "[block-dangerous-commands] [fire]" in log_text
        assert "agent=codex" in log_text


# ============================================================
# C15 doctor regression — catches the broken .mcp.json forms
# ============================================================


class TestDoctorC15Regression:
    def _make_project(self, tmp_path: Path, mcp_content: str | None) -> Path:
        import yaml as _yaml

        project = tmp_path / "proj"
        project.mkdir()
        (project / ".coding-os.yaml").write_text(
            _yaml.dump(
                {
                    "version": "1.0",
                    "agents": ["claude"],
                    "templates": [],
                    "state_dir": ".coding-os",
                }
            )
        )
        state = project / ".coding-os"
        state.mkdir()
        sqlite3.connect(str(state / "coding-os.db")).close()
        (project / "AGENTS.md").write_text("# x\n")
        (project / "Makefile").write_text("")
        (project / "docs").mkdir()
        if mcp_content is not None:
            (project / ".mcp.json").write_text(mcp_content)
        return project

    def _run_check(self, project: Path):
        from cli.doctor import DoctorReport, _check_mcp_actually_launches

        report = DoctorReport(project_dir=str(project), agent="claude", templates=[])
        _check_mcp_actually_launches(project, report)
        return next((c for c in report.checks if c.id == "mcp.actually_launches"), None)

    def test_missing_mcp_json_is_fail(self, tmp_path: Path) -> None:
        project = self._make_project(tmp_path, None)
        check = self._run_check(project)
        assert check is not None
        assert check.severity == "FAIL"
        assert "MCP config missing" in check.message

    def test_hardcoded_uv_run_directory_is_fail(self, tmp_path: Path) -> None:
        """The historical break: uv run --directory chdirs, DB path lost."""
        mcp = json.dumps(
            {
                "mcpServers": {
                    "coding-os": {
                        "command": "uv",
                        "args": [
                            "run",
                            "--directory",
                            "/does/not/exist/core/thinking_os",
                            "python",
                            "server.py",
                        ],
                    }
                }
            }
        )
        project = self._make_project(tmp_path, mcp)
        check = self._run_check(project)
        assert check is not None
        assert check.severity == "FAIL"

    def test_missing_command_is_fail(self, tmp_path: Path) -> None:
        mcp = json.dumps(
            {"mcpServers": {"coding-os": {"command": "nonexistent-cmd-xyz", "args": []}}}
        )
        project = self._make_project(tmp_path, mcp)
        check = self._run_check(project)
        assert check is not None
        assert check.severity == "FAIL"
        lowered = check.message.lower()
        assert "not found" in lowered or "crash" in lowered

    def test_wrapper_form_passes_when_cos_available(self, tmp_path: Path) -> None:
        import shutil

        if shutil.which("cos") is None:
            pytest.skip("cos not on PATH — wrapper form requires cos binary")
        mcp = json.dumps(
            {"mcpServers": {"coding-os": {"command": "cos", "args": ["server-start"]}}}
        )
        project = self._make_project(tmp_path, mcp)
        check = self._run_check(project)
        assert check is not None
        assert check.severity == "PASS", f"C15 didn't pass on wrapper: {check.message}"

    def test_codex_project_config_missing_command_is_fail(self, tmp_path: Path) -> None:
        project = self._make_project(tmp_path, None)
        (project / ".codex").mkdir(parents=True, exist_ok=True)
        (project / ".codex" / "config.toml").write_text(
            '[mcp_servers.coding-os]\nargs = ["server-start"]\n',
            encoding="utf-8",
        )
        from cli.doctor import DoctorReport, _check_mcp_actually_launches

        report = DoctorReport(project_dir=str(project), agent="codex", templates=[])
        _check_mcp_actually_launches(project, report)
        check = next((c for c in report.checks if c.id == "mcp.actually_launches"), None)
        assert check is not None
        assert check.severity == "FAIL"
        assert "no command specified" in check.message


# ============================================================
# transparency-banner — USER_BANNER inside additionalContext
# ============================================================


class TestTransparencyBanner:
    """Regression guard for `session-context.sh`'s USER_BANNER emission —
    the line `transparency-banner.md` requires the agent to echo as the
    first line of every visible reply. Covers: mode-driven verbosity,
    suppression, session-id ownership, WIP/task-current inconsistency
    warning."""

    SESSION_ID = "ses-claude-20990101-000000-abcd"

    PANEL_ID = "test-banner"

    def _setup(self, tmp_path: Path, *, mode: str = "formal") -> tuple[Path, dict]:
        state = tmp_path / ".coding-os"
        agent_dir = state / "claude"
        panel_dir = agent_dir / "panels" / self.PANEL_ID
        panel_dir.mkdir(parents=True)
        # session-id + volatile markers are panel-scoped since
        # (COS_PER_PANEL_FILES); .task-mode stays agent-scoped (shared
        # across panels of one agent). Pin COS_PANEL_ID so cos-env.sh
        # resolves a deterministic panel dir for reads/writes.
        (panel_dir / "session-id").write_text(self.SESSION_ID + "\n")
        (agent_dir / ".task-mode").write_text(mode + "\n")
        env = {
            "COS_STATE_DIR": str(state),
            "COS_AGENT": "claude",
            "COS_PANEL_ID": self.PANEL_ID,
            "CLAUDE_PROJECT_DIR": str(tmp_path),
        }
        return panel_dir, env

    def _emit(self, tmp_path: Path, env: dict) -> str:
        r = subprocess.run(
            ["bash", str(SESSION_CONTEXT)],
            input=json.dumps({"prompt": "x"}),
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(tmp_path),
            env={**os.environ, **env},
        )
        assert r.returncode == 0, r.stderr
        if not r.stdout.strip():
            return ""
        payload = json.loads(r.stdout)
        return payload["hookSpecificOutput"]["additionalContext"]

    def test_casual_query_mode_emits_minimal_banner(self, tmp_path: Path) -> None:
        _, env = self._setup(tmp_path, mode="query")
        ctx = self._emit(tmp_path, env)
        assert "USER_BANNER" in ctx
        assert "mode=query" in ctx
        # Minimal banner has NO task/gate/skill/audit fields
        assert "task=" not in ctx.split("USER_BANNER")[1]
        assert "gate=" not in ctx.split("USER_BANNER")[1]

    def test_formal_mode_emits_full_banner(self, tmp_path: Path) -> None:
        panel_dir, env = self._setup(tmp_path, mode="formal")
        (panel_dir / ".task-current").write_text(f"{self.SESSION_ID} TASK-999\n")
        (panel_dir / ".thinking_os-gate").write_text(f"{self.SESSION_ID} COMPLEX 5\n")
        (panel_dir / ".active-skill").write_text(f"{self.SESSION_ID} graph-explorer\n")
        ctx = self._emit(tmp_path, env)
        banner = ctx.split("USER_BANNER", 1)[1]
        assert "mode=formal" in banner
        assert "task=TASK-999" in banner
        assert "gate=COMPLEX 5" in banner
        assert "skill=graph-explorer" in banner

    def test_system_mode_suppresses_banner(self, tmp_path: Path) -> None:
        _, env = self._setup(tmp_path, mode="system")
        ctx = self._emit(tmp_path, env)
        # pulse line still emitted (agent-only), but no USER_BANNER directive
        assert "[coding-os pulse]" in ctx
        assert "USER_BANNER" not in ctx

    def test_stale_session_id_rejected(self, tmp_path: Path) -> None:
        """A state file written by a *different* session-id must be rejected
        so the banner doesn't echo a value the current agent never owned."""
        agent_dir, env = self._setup(tmp_path, mode="formal")
        (agent_dir / ".task-current").write_text("ses-claude-FAKE-OTHER TASK-XXX\n")
        ctx = self._emit(tmp_path, env)
        banner = ctx.split("USER_BANNER", 1)[1]
        # Stale value rejected → fallback default
        assert "task=none" in banner
        assert "TASK-XXX" not in banner

    def test_missing_session_id_file_rejects_foreign_state(self, tmp_path: Path) -> None:
        # with the panel session-id file absent, COS_PANEL_ID
        # synthesises the current session — so a state file whose owner
        # prefix doesn't match is still rejected by the ownership check.
        # (ses no longer collapses to '?'; the panel id always resolves.)
        panel_dir, env = self._setup(tmp_path, mode="formal")
        (panel_dir / "session-id").unlink()
        (panel_dir / ".task-current").write_text("ses-claude-FAKE-OTHER TASK-Y\n")
        ctx = self._emit(tmp_path, env)
        banner = ctx.split("USER_BANNER", 1)[1]
        assert "task=none" in banner
        assert "TASK-Y" not in banner

    def test_wip_without_task_emits_warn_marker(self, tmp_path: Path) -> None:
        agent_dir, env = self._setup(tmp_path, mode="formal")
        # Build a minimal DB with one in_progress task; query is
        # SELECT COUNT(*) FROM tasks WHERE status IN ('in_progress','testing').
        # We seed enough columns to satisfy NOT NULL constraints by reusing
        # the production schema via the kernel's database module.
        import sqlite3 as _sq

        db = tmp_path / ".coding-os" / "coding-os.db"
        conn = _sq.connect(db)
        conn.execute(
            "CREATE TABLE tasks ("
            "task_id TEXT PRIMARY KEY, status TEXT, title TEXT, "
            "swimlane TEXT, kind TEXT, file_path TEXT, content_hash TEXT)"
        )
        conn.execute(
            "INSERT INTO tasks VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("TASK-WARN", "in_progress", "t", "meta", "x", "/p", "h"),
        )
        conn.commit()
        conn.close()
        env["COS_DB_PATH"] = str(db)
        ctx = self._emit(tmp_path, env)
        banner = ctx.split("USER_BANNER", 1)[1]
        assert "⚠️" in banner
        assert "wip=1" in banner
        assert "task-start" in banner

    def test_banner_first_line_format_is_stable(self, tmp_path: Path) -> None:
        """The agent rule contract: banner starts with `🔔 ses=<8>` so the
        regex `^🔔 ses=` is a reliable detector. Don't break this prefix."""
        _, env = self._setup(tmp_path, mode="query")
        ctx = self._emit(tmp_path, env)
        line = ctx.split(
            "USER_BANNER (rule transparency-banner — echo as FIRST line of visible reply): ", 1
        )[1].split("\n")[0]
        assert line.startswith("🔔 ses="), f"banner prefix changed: {line!r}"
