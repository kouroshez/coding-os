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


# ============================================================
# block-migration-conflict.sh
# ============================================================


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


# ============================================================
# block-hardcoded-literals.sh
# ============================================================


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


# ============================================================
# enforce-doc-anchor.sh
# ============================================================


class TestEnforceDocAnchor:
    def test_no_anchor_blocks_code_edit(self, tmp_path: Path) -> None:
        state = tmp_path / ".coding-os"
        state.mkdir()
        r = _invoke(
            ENFORCE_DOC_ANCHOR,
            {
                "tool_name": "Write",
                "tool_input": {"file_path": "/x/cli/main.py", "content": "pass"},
            },
            env={"COS_STATE_DIR": str(state)},
        )
        assert r.returncode == 2
        assert "doc anchor" in r.stderr.lower()

    def test_placeholder_anchor_blocks(self, tmp_path: Path) -> None:
        state = tmp_path / ".coding-os"
        state.mkdir()
        (state / "session-id").write_text("ses-1\n")
        (state / ".doc-anchor").write_text("ses-1 task:X\n{to be defined}\n")
        r = _invoke(
            ENFORCE_DOC_ANCHOR,
            {
                "tool_name": "Write",
                "tool_input": {"file_path": "/x/cli/main.py", "content": "pass"},
            },
            env={"COS_STATE_DIR": str(state)},
        )
        assert r.returncode == 2

    def test_template_placeholder_bullets_block(self, tmp_path: Path) -> None:
        state = tmp_path / ".coding-os"
        state.mkdir()
        (state / "session-id").write_text("ses-1\n")
        (state / ".doc-anchor").write_text(
            "ses-1 task:X\n"
            "**REQUIRED — populate before code Write/Edit.**\n"
            "- Pre-implementation: `docs/...`\n"
            "- Post-implementation: `path/to/code.ext`\n"
        )
        r = _invoke(
            ENFORCE_DOC_ANCHOR,
            {
                "tool_name": "Write",
                "tool_input": {"file_path": "/x/cli/main.py", "content": "pass"},
            },
            env={"COS_STATE_DIR": str(state)},
        )
        assert r.returncode == 2

    def test_real_anchor_allows(self, tmp_path: Path) -> None:
        state = tmp_path / ".coding-os"
        state.mkdir()
        agent_dir = state / "claude"
        # session-id + .doc-anchor are panel-scoped since TASK-035 — the
        # hook reads them from $COS_PANEL_DIR.
        panel_dir = agent_dir / "panels" / "da-panel"
        panel_dir.mkdir(parents=True)
        (panel_dir / "session-id").write_text("ses-claude-1\n")
        (panel_dir / ".doc-anchor").write_text("ses-claude-1 task:X\ndocs/prd/01-vision.md § 3\n")
        r = _invoke(
            ENFORCE_DOC_ANCHOR,
            {
                "tool_name": "Edit",
                "tool_input": {
                    "file_path": "/x/cli/main.py",
                    "old_string": "a",
                    "new_string": "b",
                },
            },
            env={
                "COS_STATE_DIR": str(state),
                "COS_AGENT_DIR": str(agent_dir),
                "COS_AGENT": "claude",
                "COS_PANEL_ID": "da-panel",
            },
        )
        assert r.returncode == 0

    def test_session_mismatched_anchor_blocks(self, tmp_path: Path) -> None:
        state = tmp_path / ".coding-os"
        state.mkdir()
        (state / "session-id").write_text("ses-current\n")
        (state / ".doc-anchor").write_text("ses-old task:X\ndocs/prd/01-vision.md § 3\n")
        r = _invoke(
            ENFORCE_DOC_ANCHOR,
            {
                "tool_name": "Edit",
                "tool_input": {
                    "file_path": "/x/cli/main.py",
                    "old_string": "a",
                    "new_string": "b",
                },
            },
            env={"COS_STATE_DIR": str(state)},
        )
        assert r.returncode == 2
        assert "another session" in r.stderr.lower() or "session" in r.stderr.lower()

    def test_stale_legacy_anchor_blocks(self, tmp_path: Path) -> None:
        """An anchor written without the session-id header line is a legacy
        artifact; once stale, the hook blocks rather than trusting it."""
        state = tmp_path / ".coding-os"
        state.mkdir()
        agent_dir = state / "claude"
        # .doc-anchor is panel-scoped since TASK-035 — write it where the
        # hook reads it ($COS_PANEL_DIR) so the stale-legacy path is exercised.
        panel_dir = agent_dir / "panels" / "da-panel"
        panel_dir.mkdir(parents=True)
        anchor = panel_dir / ".doc-anchor"
        anchor.write_text("docs/prd/01-vision.md § 3\n")
        old = 946684800  # 2000-01-01T00:00:00Z
        os.utime(anchor, (old, old))
        r = _invoke(
            ENFORCE_DOC_ANCHOR,
            {
                "tool_name": "Edit",
                "tool_input": {
                    "file_path": "/x/cli/main.py",
                    "old_string": "a",
                    "new_string": "b",
                },
            },
            env={
                "COS_STATE_DIR": str(state),
                "COS_AGENT_DIR": str(agent_dir),
                "COS_AGENT": "claude",
                "COS_PANEL_ID": "da-panel",
            },
        )
        assert r.returncode == 2
        assert "legacy doc anchor is stale" in r.stderr.lower()

    def test_docs_edit_exempt(self, tmp_path: Path) -> None:
        """Editing docs/*.md itself doesn't require an anchor — circular."""
        state = tmp_path / ".coding-os"
        state.mkdir()
        r = _invoke(
            ENFORCE_DOC_ANCHOR,
            {
                "tool_name": "Edit",
                "tool_input": {
                    "file_path": "/x/docs/prd.md",
                    "old_string": "a",
                    "new_string": "b",
                },
            },
            env={"COS_STATE_DIR": str(state)},
        )
        assert r.returncode == 0

    def test_test_file_exempt(self, tmp_path: Path) -> None:
        state = tmp_path / ".coding-os"
        state.mkdir()
        r = _invoke(
            ENFORCE_DOC_ANCHOR,
            {
                "tool_name": "Write",
                "tool_input": {"file_path": "/x/tests/test_foo.py", "content": "x"},
            },
            env={"COS_STATE_DIR": str(state)},
        )
        assert r.returncode == 0

    def test_override_one_shot(self, tmp_path: Path) -> None:
        # Override marker lives in the agent-private dir (COS_AGENT_DIR)
        # per docs/engineering/state-files.md.
        state = tmp_path / ".coding-os"
        state.mkdir()
        agent_dir = state / "claude"
        agent_dir.mkdir()
        (agent_dir / ".doc-anchor-override").write_text("")
        r = _invoke(
            ENFORCE_DOC_ANCHOR,
            {
                "tool_name": "Write",
                "tool_input": {"file_path": "/x/cli/main.py", "content": "x"},
            },
            env={
                "COS_STATE_DIR": str(state),
                "COS_AGENT_DIR": str(agent_dir),
                "COS_AGENT": "claude",
            },
        )
        assert r.returncode == 0
        assert not (agent_dir / ".doc-anchor-override").exists()

    def test_exploratory_task_allowed(self, tmp_path: Path) -> None:
        """Task names with 'exploratory'/'spike' bypass the anchor check.
        Task marker is panel-scoped since TASK-035 — hook reads $COS_PANEL_DIR."""
        state = tmp_path / ".coding-os"
        state.mkdir()
        agent_dir = state / "claude"
        panel_dir = agent_dir / "panels" / "da-panel"
        panel_dir.mkdir(parents=True)
        (panel_dir / "session-id").write_text("ses-claude-test\n")
        (panel_dir / ".task-current").write_text("ses-claude-test exploratory-refactor\n")
        r = _invoke(
            ENFORCE_DOC_ANCHOR,
            {
                "tool_name": "Write",
                "tool_input": {"file_path": "/x/cli/main.py", "content": "x"},
            },
            env={
                "COS_STATE_DIR": str(state),
                "COS_AGENT_DIR": str(agent_dir),
                "COS_AGENT": "claude",
                "COS_PANEL_ID": "da-panel",
            },
        )
        assert r.returncode == 0


# ============================================================
# regen-reminder.sh
# ============================================================


class TestRegenReminder:
    def test_stack_yaml_triggers_regen_hint(self) -> None:
        r = _invoke(
            REGEN_REMINDER,
            {
                "tool_name": "Edit",
                "tool_input": {"file_path": "/x/templates/django/stack.yaml"},
            },
        )
        assert r.returncode == 0
        assert "regen-rules" in r.stdout
        assert "manifest-regen" in r.stdout

    def test_adapter_yaml_triggers_manifest(self) -> None:
        r = _invoke(
            REGEN_REMINDER,
            {
                "tool_name": "Edit",
                "tool_input": {"file_path": "/x/adapters/claude/adapter.yaml"},
            },
        )
        assert r.returncode == 0
        assert "manifest-regen" in r.stdout

    def test_scaffold_change_triggers_golden_hint(self) -> None:
        r = _invoke(
            REGEN_REMINDER,
            {
                "tool_name": "Write",
                "tool_input": {"file_path": "/x/templates/_base/scaffold/docs/NEW.md"},
            },
        )
        assert r.returncode == 0
        assert "capture_golden" in r.stdout

    def test_generated_rule_edit_warned(self) -> None:
        r = _invoke(
            REGEN_REMINDER,
            {
                "tool_name": "Edit",
                "tool_input": {"file_path": "/x/core/rules/dimension-registry.md"},
            },
        )
        assert r.returncode == 0
        assert "GENERATED" in r.stderr
        assert "stack.yaml" in r.stderr

    def test_generated_manifest_edit_warned(self) -> None:
        r = _invoke(
            REGEN_REMINDER,
            {
                "tool_name": "Edit",
                "tool_input": {"file_path": "/x/core/scaffold_manifest.json"},
            },
        )
        assert r.returncode == 0
        assert "GENERATED" in r.stderr

    def test_unrelated_file_silent(self) -> None:
        r = _invoke(
            REGEN_REMINDER,
            {
                "tool_name": "Edit",
                "tool_input": {"file_path": "/x/cli/main.py"},
            },
        )
        assert r.returncode == 0
        assert r.stdout.strip() == ""


# ============================================================
# test-first-reminder.sh
# ============================================================


class TestTestFirstReminder:
    @pytest.fixture
    def project(self, tmp_path: Path) -> Path:
        (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")
        (tmp_path / "src").mkdir()
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "test_bar.py").write_text("")
        return tmp_path

    def test_existing_test_file_listed(self, project: Path) -> None:
        r = _invoke(
            TEST_FIRST_REMINDER,
            {
                "tool_name": "Edit",
                "tool_input": {"file_path": str(project / "src" / "bar.py")},
            },
        )
        assert r.returncode == 0
        assert "test_bar.py" in r.stdout

    def test_no_test_file_suggests_path(self, project: Path) -> None:
        r = _invoke(
            TEST_FIRST_REMINDER,
            {
                "tool_name": "Write",
                "tool_input": {
                    "file_path": str(project / "src" / "new_module.py"),
                    "content": "",
                },
            },
        )
        assert r.returncode == 0
        assert "Suggested" in r.stdout
        assert "test_new_module.py" in r.stdout

    def test_test_file_itself_silent(self, project: Path) -> None:
        r = _invoke(
            TEST_FIRST_REMINDER,
            {
                "tool_name": "Edit",
                "tool_input": {"file_path": str(project / "tests" / "test_bar.py")},
            },
        )
        assert r.returncode == 0
        assert r.stdout.strip() == ""

    def test_migration_silent(self, project: Path) -> None:
        mig = project / "src" / "migrations" / "0001_x.py"
        mig.parent.mkdir()
        r = _invoke(
            TEST_FIRST_REMINDER,
            {
                "tool_name": "Write",
                "tool_input": {"file_path": str(mig), "content": ""},
            },
        )
        assert r.returncode == 0
        assert r.stdout.strip() == ""

    def test_non_code_silent(self, project: Path) -> None:
        r = _invoke(
            TEST_FIRST_REMINDER,
            {
                "tool_name": "Edit",
                "tool_input": {"file_path": str(project / "docs" / "x.md")},
            },
        )
        assert r.returncode == 0
        assert r.stdout.strip() == ""

    def test_tsx_file_gets_ts_test_suggestion(self, project: Path) -> None:
        r = _invoke(
            TEST_FIRST_REMINDER,
            {
                "tool_name": "Write",
                "tool_input": {
                    "file_path": str(project / "src" / "Button.tsx"),
                    "content": "",
                },
            },
        )
        assert r.returncode == 0
        assert "Button.test.tsx" in r.stdout
