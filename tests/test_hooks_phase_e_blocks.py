"""Tests for Phase E enterprise hooks (user-requested docs-first regime).

Six new hooks shipped in this phase:

  block-uv-heredoc.sh         — PreToolUse Bash — CLAUDE.md rule #9
  block-migration-conflict.sh — PreToolUse Write|Edit — rule #10
  block-hardcoded-literals.sh — PreToolUse Write|Edit — cli/*.py SSOT guard
  enforce-doc-anchor.sh       — PreToolUse Write|Edit — docs-first principle
  regen-reminder.sh           — PostToolUse Write|Edit — generated-artifact drift
  test-first-reminder.sh      — PostToolUse Write|Edit — missing-test nudge

All are agent-agnostic (live in core/hooks/) — these tests drive them
directly via stdin JSON rather than routing through Claude/Codex.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "src" / "core" / "hooks"

BLOCK_UV_HEREDOC = HOOKS_DIR / "block-uv-heredoc.sh"
BLOCK_MIGRATION_CONFLICT = HOOKS_DIR / "block-migration-conflict.sh"
BLOCK_HARDCODED_LITERALS = HOOKS_DIR / "block-hardcoded-literals.sh"
ENFORCE_DOC_ANCHOR = HOOKS_DIR / "enforce-doc-anchor.sh"
REGEN_REMINDER = HOOKS_DIR / "regen-reminder.sh"
TEST_FIRST_REMINDER = HOOKS_DIR / "test-first-reminder.sh"


def _invoke(hook: Path, payload: dict, env: dict | None = None) -> subprocess.CompletedProcess:
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    return subprocess.run(
        ["bash", str(hook)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=10,
        env=full_env,
    )


# ============================================================
# block-uv-heredoc.sh
# ============================================================


class TestBlockUvHeredoc:
    def test_non_bash_passthrough(self) -> None:
        r = _invoke(
            BLOCK_UV_HEREDOC,
            {
                "tool_name": "Edit",
                "tool_input": {"file_path": "/x.py"},
            },
        )
        assert r.returncode == 0

    def test_uv_run_with_heredoc_is_blocked(self) -> None:
        r = _invoke(
            BLOCK_UV_HEREDOC,
            {
                "tool_name": "Bash",
                "tool_input": {"command": "uv run python - <<EOF\nprint(1)\nEOF"},
            },
        )
        assert r.returncode == 2
        assert "heredoc" in r.stderr.lower()

    def test_uv_run_inside_command_sub_with_heredoc_is_blocked(self) -> None:
        r = _invoke(
            BLOCK_UV_HEREDOC,
            {
                "tool_name": "Bash",
                "tool_input": {"command": "out=$(uv run python - <<EOF\nprint(1)\nEOF\n)"},
            },
        )
        assert r.returncode == 2

    def test_plain_cat_heredoc_allowed(self) -> None:
        r = _invoke(
            BLOCK_UV_HEREDOC,
            {
                "tool_name": "Bash",
                "tool_input": {"command": "cat > x.txt <<EOF\nhi\nEOF"},
            },
        )
        assert r.returncode == 0

    def test_uv_run_without_heredoc_allowed(self) -> None:
        r = _invoke(
            BLOCK_UV_HEREDOC,
            {
                "tool_name": "Bash",
                "tool_input": {"command": "uv run pytest -q"},
            },
        )
        assert r.returncode == 0

    def test_override_consumed(self, tmp_path: Path) -> None:
        # Override lives in COS_AGENT_DIR (agent-private) per state-files.md.
        state = tmp_path / ".coding-os"
        state.mkdir()
        agent_dir = state / "claude"
        agent_dir.mkdir()
        override = agent_dir / ".uv-heredoc-override"
        override.write_text("")
        r = _invoke(
            BLOCK_UV_HEREDOC,
            {
                "tool_name": "Bash",
                "tool_input": {"command": "uv run python - <<EOF\nprint(1)\nEOF"},
            },
            env={
                "COS_STATE_DIR": str(state),
                "COS_AGENT_DIR": str(agent_dir),
                "COS_AGENT": "claude",
            },
        )
        assert r.returncode == 0
        assert not override.exists()


class TestBlockMigrationConflict:
    @pytest.fixture
    def db_py(self, tmp_path: Path) -> Path:
        path = tmp_path / "database.py"
        path.write_text(
            "MIGRATIONS = []\nMIGRATIONS.append((1, 'a', _m1))\nMIGRATIONS.append((2, 'b', _m2))\n"
        )
        return path

    def test_duplicate_version_blocked(self, db_py: Path) -> None:
        r = _invoke(
            BLOCK_MIGRATION_CONFLICT,
            {
                "tool_name": "Edit",
                "tool_input": {
                    "file_path": str(db_py),
                    "old_string": "MIGRATIONS = []",
                    "new_string": "MIGRATIONS = []\nMIGRATIONS.append((2, 'dup', _m))",
                },
            },
        )
        assert r.returncode == 2
        assert "duplicate" in r.stderr.lower()

    def test_new_next_version_allowed(self, db_py: Path) -> None:
        r = _invoke(
            BLOCK_MIGRATION_CONFLICT,
            {
                "tool_name": "Edit",
                "tool_input": {
                    "file_path": str(db_py),
                    "old_string": "_m2))",
                    "new_string": "_m2))\nMIGRATIONS.append((3, 'new', _m3))",
                },
            },
        )
        assert r.returncode == 0

    def test_rewrite_existing_version_allowed(self, db_py: Path) -> None:
        """Editing the body of an existing migration line is fine."""
        r = _invoke(
            BLOCK_MIGRATION_CONFLICT,
            {
                "tool_name": "Edit",
                "tool_input": {
                    "file_path": str(db_py),
                    "old_string": "MIGRATIONS.append((2, 'b', _m2))",
                    "new_string": "MIGRATIONS.append((2, 'b-renamed', _m2))",
                },
            },
        )
        assert r.returncode == 0

    def test_non_db_py_passthrough(self) -> None:
        r = _invoke(
            BLOCK_MIGRATION_CONFLICT,
            {
                "tool_name": "Edit",
                "tool_input": {
                    "file_path": "/x/other.py",
                    "old_string": "a",
                    "new_string": "MIGRATIONS.append((99, ...))",
                },
            },
        )
        assert r.returncode == 0

    def test_django_migration_prefix_collision(self, tmp_path: Path) -> None:
        mig_dir = tmp_path / "apps" / "x" / "migrations"
        mig_dir.mkdir(parents=True)
        (mig_dir / "0003_existing.py").write_text("")
        new_path = mig_dir / "0003_duplicate.py"
        r = _invoke(
            BLOCK_MIGRATION_CONFLICT,
            {
                "tool_name": "Write",
                "tool_input": {"file_path": str(new_path), "content": ""},
            },
        )
        assert r.returncode == 2


class TestBlockHardcodedLiterals:
    def test_django_literal_in_cli_blocked(self) -> None:
        r = _invoke(
            BLOCK_HARDCODED_LITERALS,
            {
                "tool_name": "Edit",
                "tool_input": {
                    "file_path": "src/cli/main.py",
                    "old_string": "x",
                    "new_string": 'if stack == "django":\n    pass',
                },
            },
        )
        assert r.returncode == 2

    def test_claude_literal_in_cli_blocked(self) -> None:
        r = _invoke(
            BLOCK_HARDCODED_LITERALS,
            {
                "tool_name": "Edit",
                "tool_input": {
                    "file_path": "src/cli/update.py",
                    "old_string": "x",
                    "new_string": 'if agent == "claude":',
                },
            },
        )
        assert r.returncode == 2

    def test_literal_in_comment_allowed(self) -> None:
        r = _invoke(
            BLOCK_HARDCODED_LITERALS,
            {
                "tool_name": "Edit",
                "tool_input": {
                    "file_path": "src/cli/main.py",
                    "old_string": "x",
                    "new_string": '# fallback to "claude" if none',
                },
            },
        )
        assert r.returncode == 0

    def test_literal_outside_cli_allowed(self) -> None:
        r = _invoke(
            BLOCK_HARDCODED_LITERALS,
            {
                "tool_name": "Edit",
                "tool_input": {
                    "file_path": "src/core/thinking_os/foo.py",
                    "old_string": "x",
                    "new_string": 'x = "django"',
                },
            },
        )
        assert r.returncode == 0

    def test_hyphenated_compound_allowed(self) -> None:
        """claude-code-guide is a compound, not a bare 'claude' literal."""
        r = _invoke(
            BLOCK_HARDCODED_LITERALS,
            {
                "tool_name": "Edit",
                "tool_input": {
                    "file_path": "src/cli/main.py",
                    "old_string": "x",
                    "new_string": 'skill = "claude-code-guide"',
                },
            },
        )
        assert r.returncode == 0
