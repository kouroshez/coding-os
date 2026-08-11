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
