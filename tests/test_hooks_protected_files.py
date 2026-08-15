"""block-protected-files.sh — the governance escape hatch.

Split out of test_hooks_gates.py when that file crossed the 500-line budget.
The hook has one job with its own failure modes: let a genuine governance or
docs task edit CLAUDE.md / AGENTS.md / core rules, block the same edit made as a
side effect of unrelated work, and fail closed when the active task cannot be
resolved at all.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

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

    def _with_task_doc(self, tmp_path: Path, task_id: str, title: str) -> dict[str, str]:
        """`cos task-start` writes the bare id, so the keyword the block message
        asks for is only ever in the task's own front-matter."""
        env = self._make_task_state(tmp_path, task_id)
        tasks_dir = tmp_path / "docs" / "tasks"
        tasks_dir.mkdir(parents=True, exist_ok=True)
        (tasks_dir / f"{task_id}-probe.md").write_text(
            f'---\nid: {task_id}\ntitle: "{title}"\nlabels: [ready]\n---\n', encoding="utf-8"
        )
        env["COS_PROJECT_ROOT"] = str(tmp_path)
        return env

    @staticmethod
    def _edit_payload(file_path: str) -> str:
        return json.dumps(
            {
                "tool_name": "Edit",
                "tool_input": {"file_path": file_path, "old_string": "x", "new_string": "y"},
            }
        )

    def test_bare_task_id_allows_when_the_task_title_names_governance(self, tmp_path: Path) -> None:
        env = self._with_task_doc(tmp_path, "TASK-777", "governance: retire a rule")
        result = run_hook(
            "block-protected-files.sh",
            stdin=self._edit_payload("/repo/CLAUDE.md"),
            env_overrides=env,
        )
        assert result.returncode == 0

    def test_bare_task_id_still_blocks_an_unrelated_task(self, tmp_path: Path) -> None:
        env = self._with_task_doc(tmp_path, "TASK-778", "feat: add a checkout button")
        result = run_hook(
            "block-protected-files.sh",
            stdin=self._edit_payload("/repo/CLAUDE.md"),
            env_overrides=env,
        )
        assert result.returncode == 2

    def test_unresolvable_task_id_fails_closed(self, tmp_path: Path) -> None:
        env = self._make_task_state(tmp_path, "TASK-999999")
        env["COS_PROJECT_ROOT"] = str(tmp_path)
        result = run_hook(
            "block-protected-files.sh",
            stdin=self._edit_payload("/repo/CLAUDE.md"),
            env_overrides=env,
        )
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
