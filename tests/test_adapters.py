"""
Tests for adapter installation — Claude and Codex.

Covers:
  - Claude adapter: creates .claude/, symlinks hooks/rules/skills/commands, generates settings.json, updates .mcp.json
  - Codex adapter: creates .codex/, symlinks hooks, generates hooks.json (AGENTS.md at project root is the Codex SSOT)
  - Cross-adapter: both adapters can coexist in the same project
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.slow  # whole file scaffolds sandboxes / spawns subprocesses

CODING_OS_ROOT = Path(__file__).resolve().parent.parent
ADAPTERS_DIR = CODING_OS_ROOT / "src" / "adapters"
CORE_HOOKS_DIR = CODING_OS_ROOT / "src" / "core" / "hooks"
CORE_RULES_DIR = CODING_OS_ROOT / "src" / "core" / "rules"
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


class TestClaudeAdapter:
    @pytest.fixture
    def project(self, tmp_path: Path) -> Path:
        project = tmp_path / "myproject"
        project.mkdir()
        return project

    def test_install_succeeds(self, project: Path) -> None:
        result = run_adapter_install("claude", project)
        assert result.returncode == 0, f"Install failed: {result.stderr}"

    def test_creates_claude_dir(self, project: Path) -> None:
        run_adapter_install("claude", project)
        assert (project / ".claude").is_dir()

    def test_symlinks_hooks(self, project: Path) -> None:
        run_adapter_install("claude", project)
        hooks_dir = project / ".claude" / "hooks"
        assert hooks_dir.is_dir()
        hook_files = list(hooks_dir.glob("*.sh"))
        core_hook_count = len(list(CORE_HOOKS_DIR.glob("*.sh")))
        assert len(hook_files) == core_hook_count
        # Verify they are symlinks pointing to core
        for hook in hook_files:
            assert hook.is_symlink()
            assert str(CORE_HOOKS_DIR) in str(hook.resolve())

    def test_symlinks_rules(self, project: Path) -> None:
        run_adapter_install("claude", project)
        rules_dir = project / ".claude" / "rules"
        rule_files = list(rules_dir.glob("*.md"))
        core_rule_count = len(list(CORE_RULES_DIR.glob("*.md")))
        assert len(rule_files) == core_rule_count
        for rule in rule_files:
            assert rule.is_symlink()

    def test_symlinks_skills(self, project: Path) -> None:
        run_adapter_install("claude", project)
        skills_dir = project / ".claude" / "skills"
        skill_dirs = [d for d in skills_dir.iterdir() if d.is_dir()]
        core_skill_count = len(list(CORE_SKILLS_DIR.iterdir()))
        assert len(skill_dirs) == core_skill_count
        for skill_dir in skill_dirs:
            skill_md = skill_dir / "SKILL.md"
            assert skill_md.exists()
            assert skill_md.is_symlink()

    def test_skill_overrides_skip_and_unlink(self, project: Path) -> None:
        # First install links everything; adding an override then
        # re-installing must skip AND remove the disabled skill.
        run_adapter_install("claude", project)
        assert (project / ".claude" / "skills" / "wordpress" / "SKILL.md").exists()

        overrides = project / ".coding-os" / "skill-overrides.json"
        overrides.write_text('{"disabled": ["wordpress", "supabase"]}', encoding="utf-8")
        result = run_adapter_install("claude", project)
        assert result.returncode == 0, result.stderr

        assert not (project / ".claude" / "skills" / "wordpress").exists()
        assert not (project / ".claude" / "skills" / "supabase").exists()
        assert (project / ".claude" / "skills" / "clean-code" / "SKILL.md").exists()

    def test_generates_settings_json(self, project: Path) -> None:
        run_adapter_install("claude", project)
        settings = project / ".claude" / "settings.json"
        assert settings.exists()
        data = json.loads(settings.read_text())
        assert "hooks" in data

    def test_settings_references_correct_hooks_dir(self, project: Path) -> None:
        run_adapter_install("claude", project)
        settings = project / ".claude" / "settings.json"
        content = settings.read_text()
        assert ".claude/hooks" in content
        # No unresolved template placeholders
        assert "{{HOOKS_DIR}}" not in content

    def test_creates_mcp_json(self, project: Path) -> None:
        run_adapter_install("claude", project)
        mcp_json = project / ".mcp.json"
        assert mcp_json.exists()
        data = json.loads(mcp_json.read_text())
        assert "coding-os" in data["mcpServers"]

    def test_symlinks_commands(self, project: Path) -> None:
        run_adapter_install("claude", project)
        commands_dir = project / ".claude" / "commands"
        # Hard precondition — the old `if commands_dir.exists()` guard let this
        # test pass asserting nothing when install silently skipped commands.
        assert commands_dir.is_dir(), ".claude/commands not created by install"
        cmd_files = list(commands_dir.glob("*.md"))
        assert len(cmd_files) >= 1

    def test_idempotent_install(self, project: Path) -> None:
        """Running install twice should not fail."""
        run_adapter_install("claude", project)
        result = run_adapter_install("claude", project)
        assert result.returncode == 0


# ---------------------------------------------------------------------------
# Codex Adapter
# ---------------------------------------------------------------------------


class TestCodexAdapter:
    @pytest.fixture
    def project(self, tmp_path: Path) -> Path:
        project = tmp_path / "myproject"
        project.mkdir()
        return project

    def test_install_succeeds(self, project: Path) -> None:
        result = run_adapter_install("codex", project)
        assert result.returncode == 0, f"Install failed: {result.stderr}"

    def test_creates_codex_dir(self, project: Path) -> None:
        run_adapter_install("codex", project)
        assert (project / ".codex").is_dir()

    def test_symlinks_hooks(self, project: Path) -> None:
        run_adapter_install("codex", project)
        hooks_dir = project / ".codex" / "hooks"
        assert hooks_dir.is_dir()
        hook_files = list(hooks_dir.glob("*.sh"))
        assert len(hook_files) > 0
        for hook in hook_files:
            assert hook.is_symlink()
        assert (hooks_dir / "codex-pretool-dispatch.sh").exists()
        assert (hooks_dir / "codex-sessionstart-dispatch.sh").exists()
        assert (hooks_dir / "codex-stop-dispatch.sh").exists()

    def test_generates_hooks_json(self, project: Path) -> None:
        run_adapter_install("codex", project)
        hooks_json = project / ".codex" / "hooks.json"
        assert hooks_json.exists()
        data = json.loads(hooks_json.read_text())
        assert isinstance(data, dict)
        # No unresolved template placeholders
        assert "{{HOOKS_DIR}}" not in hooks_json.read_text()
        assert str(project / ".codex" / "hooks") in hooks_json.read_text()

    def test_installed_hooks_json_uses_codex_dispatchers(self, project: Path) -> None:
        run_adapter_install("codex", project)
        hooks_json = project / ".codex" / "hooks.json"
        data = json.loads(hooks_json.read_text())

        pretool = data["hooks"]["PreToolUse"][0]["hooks"]
        assert len(pretool) == 1
        assert "codex-pretool-dispatch.sh" in pretool[0]["command"]

        startup = data["hooks"]["SessionStart"][0]["hooks"]
        assert len(startup) == 1
        assert "codex-sessionstart-dispatch.sh" in startup[0]["command"]

        stop = data["hooks"]["Stop"][0]["hooks"]
        assert len(stop) == 1
        assert "codex-stop-dispatch.sh" in stop[0]["command"]

    def test_codex_bash_hooks_are_quiet_by_default(self, project: Path) -> None:
        run_adapter_install("codex", project)
        hooks_json = project / ".codex" / "hooks.json"
        data = json.loads(hooks_json.read_text())

        pretool = data["hooks"]["PreToolUse"][0]["hooks"][0]
        posttool = data["hooks"]["PostToolUse"][0]["hooks"][0]

        assert "statusMessage" not in pretool
        assert "statusMessage" not in posttool

    def test_installed_hook_commands_work_from_nested_cwd(self, project: Path) -> None:
        run_adapter_install("codex", project)
        hooks_json = project / ".codex" / "hooks.json"
        data = json.loads(hooks_json.read_text())
        command = data["hooks"]["PreToolUse"][0]["hooks"][0]["command"]

        nested = project / "src" / "feature"
        nested.mkdir(parents=True)
        state = project / ".coding-os"
        agent_dir = state / "codex"
        agent_dir.mkdir(parents=True, exist_ok=True)
        (agent_dir / "session-id").write_text("ses-codex-test\n", encoding="utf-8")

        result = subprocess.run(
            ["/bin/sh", "-c", command],
            input=json.dumps({"tool_name": "Bash", "tool_input": {"command": "echo ok"}}),
            capture_output=True,
            text=True,
            timeout=20,
            cwd=str(nested),
            env={
                **os.environ,
                "COS_STATE_DIR": str(state),
                "COS_AGENT_DIR": str(agent_dir),
                "COS_AGENT": "codex",
            },
        )

        assert result.returncode == 0, result.stderr
        assert "No such file or directory" not in result.stderr

    def test_does_not_generate_instructions_md(self, project: Path) -> None:
        # Regression: the adapter used to generate a 48KB .codex/instructions.md
        # by concatenating core/rules + core/skills. Codex CLI does not load
        # that file — AGENTS.md at project root is the real SSOT (per
        # developers.openai.com/codex/guides/agents-md). The adapter must NOT
        # recreate it.
        run_adapter_install("codex", project)
        assert not (project / ".codex" / "instructions.md").exists()

    def test_cleans_up_legacy_instructions_md(self, project: Path) -> None:
        # A pre-existing legacy file from an older adapter version must be
        # removed on re-install so the project stays lean.
        legacy = project / ".codex" / "instructions.md"
        legacy.parent.mkdir(parents=True, exist_ok=True)
        legacy.write_text("legacy stale content")
        run_adapter_install("codex", project)
        assert not legacy.exists()

    def test_does_not_write_mcp_json(self, project: Path) -> None:
        # Codex reads MCP servers from config.toml, not .mcp.json.
        # The adapter must NOT create or touch .mcp.json — Claude's convention.
        run_adapter_install("codex", project)
        assert not (project / ".mcp.json").exists()

    def test_registers_mcp_in_codex_config(self, project: Path) -> None:
        # Symmetry with Claude's .mcp.json step: the Codex adapter must
        # register the coding-os MCP server in project-local
        # .codex/config.toml so thinking_os cognition tools are available
        # to Codex without requiring a separate manual step.
        run_adapter_install("codex", project)
        codex_cfg = project / ".codex" / "config.toml"
        assert codex_cfg.exists(), "adapter must create project-local .codex/config.toml"
        content = codex_cfg.read_text()
        assert "[mcp_servers.coding-os]" in content
        assert "[features]" in content
        assert "codex_hooks = true" in content

    def test_mcp_registration_idempotent(self, project: Path) -> None:
        # Running install twice must not duplicate the [mcp_servers.coding-os]
        # section — critical because make dogfood-full re-runs install.sh.
        run_adapter_install("codex", project)
        codex_cfg = project / ".codex" / "config.toml"
        size_after_first = codex_cfg.stat().st_size
        run_adapter_install("codex", project)
        assert codex_cfg.stat().st_size == size_after_first
        assert codex_cfg.read_text().count("[mcp_servers.coding-os]") == 1
        assert codex_cfg.read_text().count("[features]") == 1
        assert codex_cfg.read_text().count("codex_hooks = true") == 1

    def test_repairs_false_hooks_without_corrupting_next_section(self, project: Path) -> None:
        codex_cfg = project / ".codex" / "config.toml"
        codex_cfg.parent.mkdir(parents=True, exist_ok=True)
        codex_cfg.write_text(
            "[features]\n"
            "codex_hooks = false\n\n"
            "[mcp_servers.coding-os]\n"
            'command = "cos"\n'
            'args = ["server-start"]\n',
            encoding="utf-8",
        )

        run_adapter_install("codex", project)

        content = codex_cfg.read_text(encoding="utf-8")
        assert "codex_hooks = true\n\n[mcp_servers.coding-os]" in content
        assert content.count("[mcp_servers.coding-os]") == 1

    def test_repairs_stale_mcp_entry_in_place(self, project: Path) -> None:
        codex_cfg = project / ".codex" / "config.toml"
        codex_cfg.parent.mkdir(parents=True, exist_ok=True)
        codex_cfg.write_text(
            "[features]\n"
            "codex_hooks = true\n\n"
            "[mcp_servers.coding-os]\n"
            'command = "uv"\n'
            'args = ["run", "--directory", "/old/path", "python", "server.py"]\n',
            encoding="utf-8",
        )

        run_adapter_install("codex", project)

        content = codex_cfg.read_text(encoding="utf-8")
        assert content.count("[mcp_servers.coding-os]") == 1
        assert "/old/path" not in content
        assert 'command = "uv"' not in content

    def test_no_cos_fallback_uses_python_not_uv(self, project: Path) -> None:
        install_script = ADAPTERS_DIR / "codex" / "install.sh"
        env = os.environ.copy()
        env["HOME"] = str(project)
        env["PATH"] = "/usr/bin:/bin"
        result = subprocess.run(
            ["bash", str(install_script)],
            cwd=str(project),
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr
        content = (project / ".codex" / "config.toml").read_text(encoding="utf-8")
        assert 'command = "uv"' not in content
        assert "server.py" in content

    def test_symlinks_rules_mirrors_claude(self, project: Path) -> None:
        # Symmetry: every core/rules/*.md must appear as a symlink under
        # .codex/rules/ so Codex agents in consumer projects (where core/
        # is absent) can still resolve path references from AGENTS.md.
        run_adapter_install("codex", project)
        codex_rules = project / ".codex" / "rules"
        assert codex_rules.is_dir()
        source_rules = {p.name for p in CORE_RULES_DIR.glob("*.md")}
        linked = {p.name for p in codex_rules.glob("*.md")}
        assert source_rules == linked, f"missing rule symlinks: {source_rules - linked}"
        for link in codex_rules.glob("*.md"):
            assert link.is_symlink(), f"{link} is not a symlink"

    def test_symlinks_skills_mirrors_claude(self, project: Path) -> None:
        # Every core/skills/<name>/SKILL.md must appear as .codex/skills/<name>/SKILL.md.
        run_adapter_install("codex", project)
        codex_skills = project / ".codex" / "skills"
        assert codex_skills.is_dir()
        source_skills = {p.name for p in CORE_SKILLS_DIR.iterdir() if p.is_dir()}
        for skill_name in source_skills:
            link = codex_skills / skill_name / "SKILL.md"
            assert link.exists(), f"skill symlink missing: {skill_name}"
            assert link.is_symlink(), f"{link} is not a symlink"

    def test_symlinks_commands_mirrors_claude(self, project: Path) -> None:
        # Every core/commands/*.md must appear as .codex/commands/<name>.md.
        # Codex adds extra formula-f{1..11}.md symlinks (slash commands) —
        # these are codex-specific and should NOT be in core/commands/, so
        # we only assert core commands are a subset of what codex exposes.
        run_adapter_install("codex", project)
        codex_cmds = project / ".codex" / "commands"
        assert codex_cmds.is_dir()
        commands_source = CODING_OS_ROOT / "src" / "core" / "commands"
        if not commands_source.is_dir():
            return  # core has no commands — nothing to mirror
        source_cmds = {p.name for p in commands_source.glob("*.md")}
        linked = {p.name for p in codex_cmds.glob("*.md")}
        missing = source_cmds - linked
        assert not missing, f"missing command symlinks: {missing}"
        # Role-prompt slash commands (semantic naming, post-rename) — verify
        # all 11 are present. These mirror core/thinking_os/agents/<role>.md
        # and are exposed as /role-<slug> by Codex.
        expected_roles = {
            "researcher",
            "analyst",
            "architect",
            "documenter",
            "implementer",
            "reviewer",
            "debugger",
            "security_auditor",
            "deployer",
            "observer",
            "refactorer",
        }
        for role in expected_roles:
            assert f"role-{role}.md" in linked, f"role-{role}.md missing from codex commands"

    def test_idempotent_install(self, project: Path) -> None:
        run_adapter_install("codex", project)
        result = run_adapter_install("codex", project)
        assert result.returncode == 0


# ---------------------------------------------------------------------------
# Cross-Adapter Installation
# ---------------------------------------------------------------------------


class TestCrossAdapter:
    @pytest.fixture
    def project(self, tmp_path: Path) -> Path:
        project = tmp_path / "myproject"
        project.mkdir()
        return project

    def test_claude_then_codex(self, project: Path) -> None:
        """Both adapters can be installed in the same project."""
        result1 = run_adapter_install("claude", project)
        assert result1.returncode == 0
        result2 = run_adapter_install("codex", project)
        assert result2.returncode == 0

        assert (project / ".claude" / "settings.json").exists()
        assert (project / ".codex" / "hooks.json").exists()

    def test_codex_then_claude(self, project: Path) -> None:
        """Order of installation doesn't matter."""
        run_adapter_install("codex", project)
        run_adapter_install("claude", project)

        assert (project / ".claude" / "settings.json").exists()
        assert (project / ".codex" / "hooks.json").exists()

    def test_shared_state_dir(self, project: Path) -> None:
        """Both adapters create .coding-os/ state directory."""
        run_adapter_install("claude", project)
        run_adapter_install("codex", project)
        assert (project / ".coding-os").is_dir()

    def test_hooks_point_to_same_core(self, project: Path) -> None:
        """Both adapters' hooks resolve to the same core files."""
        run_adapter_install("claude", project)
        run_adapter_install("codex", project)

        claude_gate = (project / ".claude" / "hooks" / "thinking_os-gate.sh").resolve()
        codex_gate = (project / ".codex" / "hooks" / "thinking_os-gate.sh").resolve()
        assert claude_gate == codex_gate


# ---------------------------------------------------------------------------
# Stack Skill Linking (D.1 — link-stack-skills.sh helper)
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


class TestVerifyConfigPopulated:
    """`.coding-os.yaml.verify` is derived from stack VERIFY_* substitutions."""

    def test_django_populates_backend_verify(self, tmp_path: Path) -> None:
        import yaml
        from click.testing import CliRunner

        from cli.main import cli as cos_cli

        project = tmp_path / "e2e-verify"
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
        cfg = yaml.safe_load((project / ".coding-os.yaml").read_text())
        assert "verify" in cfg
        assert "backend" in cfg["verify"]
        assert "lint-backend" in cfg["verify"]["backend"]


class TestMcpPortable:
    """`.mcp.json` uses `cos server-start` wrapper when cos is on PATH."""

    def test_mcp_entry_uses_wrapper_when_cos_available(self, tmp_path: Path) -> None:
        """When `cos` is on PATH, entry should be the canonical fast-path
        entry. Per CLAUDE.md rule 20, ``cos-mcp-start`` is preferred —
        it skips cli.main's 380 ms subcommand-import tax that breaks
        the Anthropic VSCode extension's 60s init budget.  Both
        ``cos-mcp-start`` and the legacy ``cos``/``uv`` shapes are
        accepted (the renderer falls back when the fast-path binary
        isn't installed)."""
        import shutil as _shutil

        if _shutil.which("cos") is None:
            pytest.skip("cos not on PATH")
        project = tmp_path / "proj"
        project.mkdir()
        result = run_adapter_install("claude", project)
        assert result.returncode == 0
        data = json.loads((project / ".mcp.json").read_text())
        entry = data["mcpServers"]["coding-os"]
        assert entry["command"] in ("cos-mcp-start", "cos", "uv")
