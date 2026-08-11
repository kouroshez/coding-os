"""
Tests for adapter installation — Claude and Codex.

Covers:
  - Claude adapter: creates .claude/, symlinks hooks/rules/skills/commands, generates settings.json, updates .mcp.json
  - Codex adapter: creates .codex/, symlinks hooks, generates hooks.json (AGENTS.md at project root is the Codex SSOT)
  - Cross-adapter: both adapters can coexist in the same project
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.slow  # whole file scaffolds sandboxes / spawns subprocesses

CODING_OS_ROOT = Path(__file__).resolve().parent.parent
ADAPTERS_DIR = CODING_OS_ROOT / "src" / "adapters"
CORE_HOOKS_DIR = CODING_OS_ROOT / "src" / "core" / "hooks"
CORE_RULES_DIR = CODING_OS_ROOT / "src" / "core" / "rules"
# Derived full-catalog matrices that install-adapter.sh deliberately does NOT
# symlink as always-active rules — the SessionStart skill_primer card + inline
# enforce-skill.sh cover them (TASK-466 / audit C1). Keep in sync with
# install-adapter.sh::_NON_ACTIVE_RULES.
NON_ACTIVE_RULES = {"dimension-registry.md", "skill-enforcement.md"}
CORE_SKILLS_DIR = CODING_OS_ROOT / "src" / "core" / "skills"
LINK_STACK_SKILLS = CODING_OS_ROOT / "src" / "core" / "scripts" / "link-stack-skills.sh"


def run_adapter_install(adapter: str, project_dir: Path) -> subprocess.CompletedProcess:
    """Run an adapter install script in a project directory.

    HOME is still redirected into the fixture so any fallback reads of
    ~/.codex/config.toml stay hermetic, but the Codex adapter itself now
    writes project-scoped config at .codex/config.toml.
    """
    install_script = ADAPTERS_DIR / adapter / "install.sh"
    env = os.environ.copy()
    env["HOME"] = str(project_dir)
    return subprocess.run(
        ["bash", str(install_script)],
        cwd=str(project_dir),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


# ---------------------------------------------------------------------------
# Claude Adapter
# ---------------------------------------------------------------------------


class TestStackSkillLinking:
    @pytest.fixture
    def project(self, tmp_path: Path) -> Path:
        project = tmp_path / "myproject"
        project.mkdir()
        (project / ".claude" / "skills").mkdir(parents=True)
        return project

    def _run_linker(self, project: Path, *stacks: str) -> subprocess.CompletedProcess:
        agent_skills = str(project / ".claude" / "skills")
        return subprocess.run(
            [
                "bash",
                str(LINK_STACK_SKILLS),
                agent_skills,
                # link-stack-skills.sh now takes the DATA root (dir containing
                # templates/), not the repo root — wheel-compatible (TASK-219).
                str(CODING_OS_ROOT / "src"),
                *stacks,
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )

    def test_django_links_python_django(self, project: Path) -> None:
        result = self._run_linker(project, "django")
        assert result.returncode == 0, result.stderr
        link = project / ".claude" / "skills" / "python-django" / "SKILL.md"
        assert link.is_symlink()
        assert link.resolve().exists()

    def test_nextjs_links_stack_skill(self, project: Path) -> None:
        # frontend-design moved to core/universal skills (f3dd97d8); it is now
        # linked for every project by the core-skill linker, NOT by this
        # per-stack linker — so the stack linker emits only nextjs-react.
        result = self._run_linker(project, "nextjs")
        assert result.returncode == 0, result.stderr
        assert (project / ".claude/skills/nextjs-react/SKILL.md").is_symlink()

    def test_multiple_stacks_link_all(self, project: Path) -> None:
        # Only per-stack skills are asserted here; frontend-design is a core
        # skill (f3dd97d8), linked universally, not by this stack linker.
        self._run_linker(project, "django", "nextjs")
        assert (project / ".claude/skills/python-django/SKILL.md").exists()
        assert (project / ".claude/skills/nextjs-react/SKILL.md").exists()

    def test_unknown_stack_is_silent_skip(self, project: Path) -> None:
        result = self._run_linker(project, "nonexistent-stack-xyz")
        assert result.returncode == 0
        # Nothing should be linked
        assert not list((project / ".claude" / "skills").iterdir())

    def test_idempotent_re_link(self, project: Path) -> None:
        self._run_linker(project, "django")
        first = (project / ".claude/skills/python-django/SKILL.md").resolve()
        self._run_linker(project, "django")
        second = (project / ".claude/skills/python-django/SKILL.md").resolve()
        assert first == second

    def test_rejects_too_few_args(self) -> None:
        result = subprocess.run(
            ["bash", str(LINK_STACK_SKILLS), "only-one"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert result.returncode == 64


class TestInitLinksStackSkills:
    """End-to-end: `cos init -t django` leaves python-django linked."""

    def test_init_with_django_links_skill(self, tmp_path: Path) -> None:
        from click.testing import CliRunner

        from cli.main import cli as cos_cli

        project = tmp_path / "e2e"
        project.mkdir()
        runner = CliRunner()
        result = runner.invoke(
            cos_cli,
            [
                "init",
                "--agent",
                "claude",
                "--template",
                "django",
                "--project-dir",
                str(project),
                "--no-git",
            ],
        )
        assert result.exit_code == 0, result.output
        skill = project / ".claude/skills/python-django/SKILL.md"
        assert skill.exists(), f"python-django SKILL.md not linked. Output:\n{result.output}"
        assert skill.is_symlink()

    def test_init_with_nextjs_links_both(self, tmp_path: Path) -> None:
        from click.testing import CliRunner

        from cli.main import cli as cos_cli

        project = tmp_path / "e2e"
        project.mkdir()
        runner = CliRunner()
        result = runner.invoke(
            cos_cli,
            [
                "init",
                "--agent",
                "claude",
                "--template",
                "nextjs",
                "--project-dir",
                str(project),
                "--no-git",
            ],
        )
        assert result.exit_code == 0, result.output
        assert (project / ".claude/skills/nextjs-react/SKILL.md").exists()
        assert (project / ".claude/skills/frontend-design/SKILL.md").exists()
