"""
Tests for core/hooks/ — parameterization, syntax, and COS_STATE_DIR support.

Covers:
  - All hooks pass bash -n syntax check
  - cos-env.sh sets correct defaults
  - cos-env.sh respects COS_STATE_DIR override
  - write-state.sh and check-state.sh round-trip
  - Gate hooks respond to correct state values
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).resolve().parent.parent / "src" / "core" / "hooks"


def run_hook(
    hook_name: str,
    stdin: str = "",
    env_overrides: dict[str, str] | None = None,
    cwd: str | None = None,
) -> subprocess.CompletedProcess:
    """Run a hook script with optional stdin and environment overrides."""
    hook_path = HOOKS_DIR / hook_name
    env = os.environ.copy()
    if env_overrides:
        env.update(env_overrides)
    return subprocess.run(
        ["bash", str(hook_path)],
        input=stdin,
        capture_output=True,
        text=True,
        env=env,
        cwd=cwd,
        timeout=10,
    )


REPO_SRC = HOOKS_DIR.parent.parent  # <repo>/src — for the canonical Python resolver


def _resolve_cos_var(
    var: str,
    cwd: str,
    env_overrides: dict[str, str] | None = None,
    strip: tuple[str, ...] = ("CLAUDE_PROJECT_DIR", "COS_PROJECT_ROOT", "COS_STATE_DIR"),
) -> str:
    """Source cos-env.sh from `cwd` and echo one exported var. The anchor env
    vars in `strip` are removed first so the upward marker-walk path runs."""
    env = {k: v for k, v in os.environ.items() if k not in strip}
    if env_overrides:
        env.update(env_overrides)
    script = 'source "{}"; echo "${}"'.format(HOOKS_DIR / "cos-env.sh", var)
    return subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        cwd=cwd,
        env=env,
        timeout=10,
    ).stdout.strip()


def _python_resolve_root(cwd: str) -> str:
    """Project root per the canonical Python resolver, run from `cwd`."""
    import sys

    code = (
        f"import sys; sys.path.insert(0, {str(REPO_SRC)!r}); "
        "from core.thinking_os._db_paths import _find_project_root_from_cwd; "
        "print(_find_project_root_from_cwd())"
    )
    return subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=cwd,
        timeout=30,
    ).stdout.strip()


# ---------------------------------------------------------------------------
# Syntax validation — all hooks must pass bash -n
# ---------------------------------------------------------------------------


class TestThinkingOsGate:
    @pytest.fixture
    def gate_env(self, tmp_path: Path) -> tuple[Path, dict[str, str]]:
        """Set up a temp project with session + panel-scoped state dir
        (TASK-035: cognitive state lives at $COS_PANEL_DIR, not $COS_AGENT_DIR)."""
        state_dir = tmp_path / ".coding-os"
        state_dir.mkdir()
        agent_dir = state_dir / "claude"
        agent_dir.mkdir()
        panel_id = "test-gate-panel"
        panel_dir = agent_dir / "panels" / panel_id
        panel_dir.mkdir(parents=True)
        session_id = "ses-claude-20260405-120000-ABCD"
        session_file = panel_dir / "session-id"
        session_file.write_text(session_id)
        env = {
            **os.environ,
            "COS_STATE_DIR": str(state_dir),
            "COS_AGENT_DIR": str(agent_dir),
            "COS_PANEL_ID": panel_id,
            "COS_PANEL_DIR": str(panel_dir),
            "COS_SESSION_FILE": str(session_file),
            "COS_AGENT": "claude",
        }
        return tmp_path, env

    def _write_gate(self, state_dir: Path, session_id: str, value: str) -> None:
        # Gate is per-panel. Use the same panel-id as gate_env.
        gate_file = state_dir / "claude" / "panels" / "test-gate-panel" / ".thinking_os-gate"
        gate_file.write_text(f"{session_id} {value}")

    def test_blocks_py_without_gate(self, gate_env: tuple[Path, dict]) -> None:
        tmp_path, env = gate_env
        payload = json.dumps(
            {
                "tool_name": "Edit",
                "tool_input": {"file_path": "app/main.py", "old_string": "x", "new_string": "y"},
            }
        )
        result = run_hook(
            "thinking_os-gate.sh", stdin=payload, env_overrides=env, cwd=str(tmp_path)
        )
        assert result.returncode == 2

    def test_allows_py_with_valid_gate(self, gate_env: tuple[Path, dict]) -> None:
        tmp_path, env = gate_env
        state_dir = Path(env["COS_STATE_DIR"])
        session_id = Path(env["COS_SESSION_FILE"]).read_text().strip()
        self._write_gate(state_dir, session_id, "CLEAR 1")
        payload = json.dumps(
            {
                "tool_name": "Edit",
                "tool_input": {"file_path": "app/main.py", "old_string": "x", "new_string": "y"},
            }
        )
        result = run_hook(
            "thinking_os-gate.sh", stdin=payload, env_overrides=env, cwd=str(tmp_path)
        )
        assert result.returncode == 0

    def test_allows_md_without_gate(self, gate_env: tuple[Path, dict]) -> None:
        tmp_path, env = gate_env
        payload = json.dumps(
            {
                "tool_name": "Edit",
                "tool_input": {"file_path": "docs/readme.md", "old_string": "x", "new_string": "y"},
            }
        )
        result = run_hook(
            "thinking_os-gate.sh", stdin=payload, env_overrides=env, cwd=str(tmp_path)
        )
        assert result.returncode == 0

    def test_allows_test_file_without_gate(self, gate_env: tuple[Path, dict]) -> None:
        tmp_path, env = gate_env
        payload = json.dumps(
            {
                "tool_name": "Edit",
                "tool_input": {
                    "file_path": "tests/test_main.py",
                    "old_string": "x",
                    "new_string": "y",
                },
            }
        )
        result = run_hook(
            "thinking_os-gate.sh", stdin=payload, env_overrides=env, cwd=str(tmp_path)
        )
        assert result.returncode == 0


class TestBlockProtectedFilesGovernanceEscape:
    """Regression tests for the task-name-based escape hatch in
    block-protected-files.sh.

    The hook must:
      - Block CLAUDE.md / AGENTS.md / core/rules edits when the active
        task has a generic name like 'feature-auth'.
      - Allow the same edits when the active task name matches governance
        patterns (docs-update, governance, claude-md-update, ...).

    This lets legitimate docs maintenance work proceed while keeping the
    safety net in place for accidental side-effect edits.
    """

    def _make_task_state(self, tmp_path: Path, task_name: str) -> dict[str, str]:
        """Build an env that points the hook at a temp panel-scoped state dir
        with a pre-written session-scoped .task-current file. Matches the
        post-TASK-035 layout: shared root + claude/ + panels/<panel-id>/."""
        state_dir = tmp_path / ".coding-os"
        state_dir.mkdir()
        agent_dir = state_dir / "claude"
        agent_dir.mkdir()
        panel_id = "test-protect-panel"
        panel_dir = agent_dir / "panels" / panel_id
        panel_dir.mkdir(parents=True)
        session_id = "ses-claude-20260407-120000-TEST"
        (panel_dir / "session-id").write_text(session_id)
        (panel_dir / ".task-current").write_text(f"{session_id} {task_name}")
        return {
            "COS_STATE_DIR": str(state_dir),
            "COS_AGENT_DIR": str(agent_dir),
            "COS_PANEL_ID": panel_id,
            "COS_PANEL_DIR": str(panel_dir),
            "COS_SESSION_FILE": str(panel_dir / "session-id"),
            "COS_AGENT": "claude",
        }

    def test_blocks_claude_md_with_unrelated_task(self, tmp_path: Path) -> None:
        env = self._make_task_state(tmp_path, "feature-auth-flow")
        payload = json.dumps(
            {
                "tool_name": "Edit",
                "tool_input": {
                    "file_path": "/repo/CLAUDE.md",
                    "old_string": "x",
                    "new_string": "y",
                },
            }
        )
        result = run_hook("block-protected-files.sh", stdin=payload, env_overrides=env)
        assert result.returncode == 2

    def test_allows_claude_md_with_docs_update_task(self, tmp_path: Path) -> None:
        env = self._make_task_state(tmp_path, "docs-update-phase-d")
        payload = json.dumps(
            {
                "tool_name": "Edit",
                "tool_input": {
                    "file_path": "/repo/CLAUDE.md",
                    "old_string": "x",
                    "new_string": "y",
                },
            }
        )
        result = run_hook("block-protected-files.sh", stdin=payload, env_overrides=env)
        assert result.returncode == 0

    def test_allows_agents_md_with_governance_task(self, tmp_path: Path) -> None:
        env = self._make_task_state(tmp_path, "governance-refactor")
        payload = json.dumps(
            {
                "tool_name": "Edit",
                "tool_input": {
                    "file_path": "/repo/AGENTS.md",
                    "old_string": "x",
                    "new_string": "y",
                },
            }
        )
        result = run_hook("block-protected-files.sh", stdin=payload, env_overrides=env)
        assert result.returncode == 0

    def test_blocks_core_rules_with_unrelated_task(self, tmp_path: Path) -> None:
        env = self._make_task_state(tmp_path, "feature-checkout")
        payload = json.dumps(
            {
                "tool_name": "Edit",
                "tool_input": {
                    "file_path": "/repo/.claude/rules/memory.md",
                    "old_string": "x",
                    "new_string": "y",
                },
            }
        )
        result = run_hook("block-protected-files.sh", stdin=payload, env_overrides=env)
        assert result.returncode == 2

    def test_allows_normal_file_edit_regardless_of_task(self, tmp_path: Path) -> None:
        """Non-governance files are always allowed — the task-name filter
        only gates governance files."""
        env = self._make_task_state(tmp_path, "feature-cart")
        payload = json.dumps(
            {
                "tool_name": "Edit",
                "tool_input": {
                    "file_path": "backend/apps/cart/services.py",
                    "old_string": "x",
                    "new_string": "y",
                },
            }
        )
        result = run_hook("block-protected-files.sh", stdin=payload, env_overrides=env)
        assert result.returncode == 0

    def test_allows_agents_md_with_multiword_governance_marker(self, tmp_path: Path) -> None:
        """Regression (TASK-097): a multi-word marker whose governance keyword
        is NOT the last token must still be recognised. The old `${VALUE##* }`
        extraction kept only the last word ('align-docs') and false-blocked."""
        env = self._make_task_state(tmp_path, "docs-update TASK-096 align-docs")
        payload = json.dumps(
            {
                "tool_name": "Edit",
                "tool_input": {
                    "file_path": "/repo/AGENTS.md",
                    "old_string": "x",
                    "new_string": "y",
                },
            }
        )
        result = run_hook("block-protected-files.sh", stdin=payload, env_overrides=env)
        assert result.returncode == 0

    def test_blocks_multiword_nongovernance_marker(self, tmp_path: Path) -> None:
        """The wider match must NOT leak: a multi-word non-governance marker
        still blocks governance edits."""
        env = self._make_task_state(tmp_path, "implement TASK-100 feature-auth")
        payload = json.dumps(
            {
                "tool_name": "Edit",
                "tool_input": {
                    "file_path": "/repo/AGENTS.md",
                    "old_string": "x",
                    "new_string": "y",
                },
            }
        )
        result = run_hook("block-protected-files.sh", stdin=payload, env_overrides=env)
        assert result.returncode == 2

    def test_blocks_core_skills_source_with_unrelated_task(self, tmp_path: Path) -> None:
        """The src/core/skills SOURCE (not just its rendered .claude copy) is
        protected DNA: it propagates to every consumer via live symlinks, so a
        skill-body edit under an unrelated task must block."""
        env = self._make_task_state(tmp_path, "feature-search")
        payload = json.dumps(
            {
                "tool_name": "Edit",
                "tool_input": {
                    "file_path": "/repo/src/core/skills/clean-code/SKILL.md",
                    "old_string": "x",
                    "new_string": "y",
                },
            }
        )
        result = run_hook("block-protected-files.sh", stdin=payload, env_overrides=env)
        assert result.returncode == 2

    def test_allows_core_skills_source_with_governance_task(self, tmp_path: Path) -> None:
        env = self._make_task_state(tmp_path, "docs-update refine-skill")
        payload = json.dumps(
            {
                "tool_name": "Edit",
                "tool_input": {
                    "file_path": "/repo/src/core/skills/clean-code/SKILL.md",
                    "old_string": "x",
                    "new_string": "y",
                },
            }
        )
        result = run_hook("block-protected-files.sh", stdin=payload, env_overrides=env)
        assert result.returncode == 0

    def test_blocks_core_rules_source_with_unrelated_task(self, tmp_path: Path) -> None:
        """The src/core/rules SOURCE mirrors the skills case."""
        env = self._make_task_state(tmp_path, "feature-cart")
        payload = json.dumps(
            {
                "tool_name": "Edit",
                "tool_input": {
                    "file_path": "/repo/src/core/rules/anti-overengineering.md",
                    "old_string": "x",
                    "new_string": "y",
                },
            }
        )
        result = run_hook("block-protected-files.sh", stdin=payload, env_overrides=env)
        assert result.returncode == 2


class TestSessionEndUncommittedAdvisory:
    """TASK-564: session-end.sh advises on uncommitted NON-docs code at end-of-turn,
    excludes docs/ board churn, stays fail-open, and does NOT duplicate the
    still-open-task nudge (that lives in warn-abandoned-task.sh)."""

    def _run(
        self, tmp_path: Path, mutate, run_subdir: str | None = None
    ) -> subprocess.CompletedProcess:
        repo = tmp_path / "repo"
        (repo / "src").mkdir(parents=True)
        (repo / "docs" / "tasks").mkdir(parents=True)
        # Neutral hooks dir OUTSIDE the repo so a globally-installed core.hooksPath
        # can't block the baseline commit and isn't seen by git status.
        nohooks = tmp_path / "nohooks"
        nohooks.mkdir()

        def git(*args: str) -> None:
            subprocess.run(["git", *args], cwd=str(repo), check=True, capture_output=True)

        git("init", "-q")
        git("config", "user.email", "t@example.com")
        git("config", "user.name", "t")
        git("config", "core.hooksPath", str(nohooks))
        # Ignore state dirs cos-env/the hook may create so they don't read as
        # uncommitted code and poison the advisory under test.
        (repo / ".gitignore").write_text(".coding-os/\n.cos-state/\n")
        (repo / "src" / "app.py").write_text("x = 1\n")
        (repo / "docs" / "tasks" / "TASK-1.md").write_text("# task\n")
        git("add", "-A")
        git("commit", "-qm", "base")

        state = repo / ".cos-state"
        state.mkdir()
        db = state / "coding-os.db"
        db.write_text("")  # stub so session-end.sh proceeds past its DB gate

        mutate(repo)
        return subprocess.run(
            ["bash", str(HOOKS_DIR / "session-end.sh")],
            input='{"session_id": "test-sess-564"}',
            capture_output=True,
            text=True,
            cwd=str(repo / run_subdir) if run_subdir else str(repo),
            timeout=20,
            env={
                **os.environ,
                "COS_DB_PATH": str(db),
                "COS_AGENT": "claude",
                "COS_PANEL_ID": "p564",
            },
        )

    def test_advises_on_uncommitted_code(self, tmp_path: Path) -> None:
        result = self._run(tmp_path, lambda repo: (repo / "src" / "app.py").write_text("x = 2\n"))
        assert result.returncode == 0
        assert "uncommitted code change" in result.stderr

    def test_silent_when_only_board_files_changed(self, tmp_path: Path) -> None:
        # docs/tasks board churn must NOT trip the code advisory (`:(exclude)docs`).
        result = self._run(
            tmp_path, lambda repo: (repo / "docs" / "tasks" / "TASK-1.md").write_text("# edited\n")
        )
        assert result.returncode == 0
        assert "uncommitted code change" not in result.stderr

    def test_silent_on_clean_tree(self, tmp_path: Path) -> None:
        result = self._run(tmp_path, lambda repo: None)
        assert result.returncode == 0
        assert "uncommitted code change" not in result.stderr

    def test_advises_from_subdir_about_root_change(self, tmp_path: Path) -> None:
        # TASK-566 J: a Stop firing from a SUBDIR must still see a root-level change —
        # the cwd-relative `git status -- .` only saw the subtree and missed it.
        result = self._run(
            tmp_path,
            lambda repo: (repo / "rootcode.py").write_text("y = 1\n"),
            run_subdir="src",
        )
        assert result.returncode == 0
        assert "uncommitted code change" in result.stderr

    def test_advises_on_non_md_docs_asset(self, tmp_path: Path) -> None:
        # TASK-566 N: an uncommitted NON-.md file under docs/ (a png/json asset) was
        # counted by neither advisory; the docs advisory must now surface it.
        def mutate(repo: Path) -> None:
            (repo / "docs" / "assets").mkdir(parents=True, exist_ok=True)
            (repo / "docs" / "assets" / "diagram.png").write_text("PNGDATA\n")

        result = self._run(tmp_path, mutate)
        assert result.returncode == 0
        assert "uncommitted doc(s)" in result.stderr
