"""Tests for two session-added hooks (user-requested):

  core/hooks/enforce-template.sh       — blocks raw Write on structured .md
                                         paths, redirects to make/cos/MCP tools
  core/hooks/enforce-doc-sync.sh       — companion-doc hints after code
                                         changes (absorbed doc-sync-reminder.sh)

Both are agent-agnostic (live in core/hooks/) — they're symlinked into
every project via adapter install, so these tests drive them directly
through stdin JSON rather than going through Claude/Codex harnesses.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "src" / "core" / "hooks"
ENFORCE_TEMPLATE = HOOKS_DIR / "enforce-template.sh"
ENFORCE_DOC_SYNC = HOOKS_DIR / "enforce-doc-sync.sh"


def _invoke(hook: Path, payload: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(hook)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=5,
    )


# ---------------------------------------------------------------------------
# enforce-template.sh
# ---------------------------------------------------------------------------


class TestEnforceTemplate:
    def test_hook_is_executable(self) -> None:
        assert ENFORCE_TEMPLATE.exists()
        assert os.access(ENFORCE_TEMPLATE, os.X_OK)

    def test_non_write_tool_is_passthrough(self, tmp_path: Path) -> None:
        target = tmp_path / "docs" / "tasks" / "TASK-099-x.md"
        result = _invoke(
            ENFORCE_TEMPLATE,
            {
                "tool_name": "Edit",
                "tool_input": {"file_path": str(target)},
            },
        )
        assert result.returncode == 0, result.stderr

    def test_non_md_file_is_passthrough(self, tmp_path: Path) -> None:
        target = tmp_path / "docs" / "tasks" / "script.py"
        result = _invoke(
            ENFORCE_TEMPLATE,
            {
                "tool_name": "Write",
                "tool_input": {"file_path": str(target)},
            },
        )
        assert result.returncode == 0

    def test_existing_file_is_passthrough(self, tmp_path: Path) -> None:
        target = tmp_path / "docs" / "tasks" / "TASK-099-existing.md"
        target.parent.mkdir(parents=True)
        target.write_text("already here")
        result = _invoke(
            ENFORCE_TEMPLATE,
            {
                "tool_name": "Write",
                "tool_input": {"file_path": str(target)},
            },
        )
        assert result.returncode == 0

    def test_new_task_file_is_blocked(self, tmp_path: Path) -> None:
        target = tmp_path / "docs" / "tasks" / "TASK-042-new.md"
        result = _invoke(
            ENFORCE_TEMPLATE,
            {
                "tool_name": "Write",
                "tool_input": {"file_path": str(target)},
            },
        )
        assert result.returncode == 2
        assert "task-create" in result.stderr
        assert "template" in result.stderr.lower()

    def test_new_adr_soft_reminder_without_template(self, tmp_path: Path) -> None:
        target = tmp_path / "docs" / "architecture" / "adr" / "ADR-007-new.md"
        result = _invoke(
            ENFORCE_TEMPLATE,
            {
                "tool_name": "Write",
                "tool_input": {"file_path": str(target)},
            },
        )
        assert result.returncode == 0
        assert "ADR" in result.stderr or "Status" in result.stderr

    def test_new_adr_blocked_with_template(self, tmp_path: Path) -> None:
        template_dir = tmp_path / "docs" / "governance" / "_templates"
        template_dir.mkdir(parents=True)
        (template_dir / "adr-template.md").write_text("## Status\n")
        target = tmp_path / "docs" / "architecture" / "adr" / "ADR-008-new.md"
        result = _invoke(
            ENFORCE_TEMPLATE,
            {
                "tool_name": "Write",
                "tool_input": {"file_path": str(target)},
            },
        )
        assert result.returncode == 2
        assert "ADR template" in result.stderr

    def test_new_prd_file_is_blocked(self, tmp_path: Path) -> None:
        target = tmp_path / "docs" / "prd" / "01-snapshot-vision.md"
        result = _invoke(
            ENFORCE_TEMPLATE,
            {
                "tool_name": "Write",
                "tool_input": {"file_path": str(target)},
            },
        )
        assert result.returncode == 2
        assert "cos setup" in result.stderr

    def test_new_breakthrough_file_is_blocked(self, tmp_path: Path) -> None:
        target = tmp_path / "docs" / "insights" / "TASK-042-insight.md"
        result = _invoke(
            ENFORCE_TEMPLATE,
            {
                "tool_name": "Write",
                "tool_input": {"file_path": str(target)},
            },
        )
        assert result.returncode == 2
        assert "cos_learn_narrative" in result.stderr

    def test_breakthrough_index_is_allowed(self, tmp_path: Path) -> None:
        target = tmp_path / "docs" / "insights" / "00-index.md"
        result = _invoke(
            ENFORCE_TEMPLATE,
            {
                "tool_name": "Write",
                "tool_input": {"file_path": str(target)},
            },
        )
        assert result.returncode == 0

    def test_freeform_playbook_is_allowed(self, tmp_path: Path) -> None:
        target = tmp_path / "docs" / "playbooks" / "new-playbook.md"
        result = _invoke(
            ENFORCE_TEMPLATE,
            {
                "tool_name": "Write",
                "tool_input": {"file_path": str(target)},
            },
        )
        assert result.returncode == 0

    def test_escape_hatch_override(self, tmp_path: Path) -> None:
        # Override lives in the agent-private dir now — the one-shot bypass
        # must not leak across concurrent agents.
        state = tmp_path / ".coding-os"
        state.mkdir()
        agent_dir = state / "claude"
        agent_dir.mkdir()
        override = agent_dir / ".template-override"
        override.write_text("")
        target = tmp_path / "docs" / "tasks" / "TASK-099-override.md"
        env = os.environ.copy()
        env["COS_STATE_DIR"] = str(state)
        env["COS_AGENT_DIR"] = str(agent_dir)
        env["COS_AGENT"] = "claude"
        result = subprocess.run(
            ["bash", str(ENFORCE_TEMPLATE)],
            input=json.dumps(
                {
                    "tool_name": "Write",
                    "tool_input": {"file_path": str(target)},
                }
            ),
            capture_output=True,
            text=True,
            env=env,
            timeout=5,
        )
        assert result.returncode == 0
        assert not override.exists(), "override must be one-shot"


# ---------------------------------------------------------------------------
# enforce-doc-sync.sh — companion-doc hints (the old doc-sync-reminder.sh is
# now a stub; its behaviour was absorbed here). The stub no-op tests were
# removed — verifying a stub returns 0 carries no signal.
# ---------------------------------------------------------------------------


class TestEnforceDocSync:
    def test_cli_py_prints_cli_companion_doc(self, tmp_path: Path) -> None:
        # enforce-doc-sync.sh absorbed companion-doc hints from doc-sync-reminder.sh.
        # Output goes to stderr; file must exist for the hook to proceed past the
        # `[[ ! -f FILE_PATH ]]` early-exit guard. The cli/ map now points at the
        # meta-project CLI section (the old README/features pair was refined out).
        target = tmp_path / "src" / "cli" / "main.py"
        target.parent.mkdir(parents=True)
        target.write_text("# test\n")
        result = _invoke(
            ENFORCE_DOC_SYNC,
            {
                "tool_name": "Edit",
                "tool_input": {"file_path": str(target)},
            },
        )
        assert result.returncode == 0
        assert "meta-project.md" in result.stderr

    def test_server_py_prints_mcp_docs(self, tmp_path: Path) -> None:
        target = tmp_path / "src" / "core" / "thinking_os" / "server.py"
        target.parent.mkdir(parents=True)
        target.write_text("# test\n")
        result = _invoke(
            ENFORCE_DOC_SYNC,
            {
                "tool_name": "Edit",
                "tool_input": {"file_path": str(target)},
            },
        )
        assert result.returncode == 0
        # server.py maps to the MCP docs (mcp-tool-inventory / mcp-error-envelope).
        assert "mcp" in result.stderr.lower()

    def test_hook_script_prints_hook_docs(self, tmp_path: Path) -> None:
        target = tmp_path / "src" / "core" / "hooks" / "new-hook.sh"
        target.parent.mkdir(parents=True)
        target.write_text("#!/bin/bash\n")
        result = _invoke(
            ENFORCE_DOC_SYNC,
            {
                "tool_name": "Write",
                "tool_input": {"file_path": str(target)},
            },
        )
        assert result.returncode == 0
        assert "hook" in result.stderr.lower()
