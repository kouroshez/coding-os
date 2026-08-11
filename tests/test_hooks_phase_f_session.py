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
        # The command must carry one of the hook's trigger literals ("git push"
        # here) or the fast-skip returns before the fire log ever runs — a plain
        # `ls -la` exits at the no-match short-circuit. Non-force push to a
        # feature branch reaches the log and is still allowed.
        p = {"tool_name": "Bash", "tool_input": {"command": "git push origin feature-x"}}
        r = _invoke(BLOCK_DANGEROUS_COMMANDS, p, env=env)
        assert r.returncode == 0
        log_text = (state / ".hooks.log").read_text()
        assert "[block-dangerous-commands] [fire]" in log_text
        assert "agent=codex" in log_text


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
        _agent_dir, env = self._setup(tmp_path, mode="formal")
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
