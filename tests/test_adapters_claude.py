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


class TestClaudeAdapter:
    @pytest.fixture
    def project(self, tmp_path: Path) -> Path:
        project = tmp_path / "myproject"
        project.mkdir()
        return project

    @pytest.fixture(scope="class")
    def installed(self, tmp_path_factory: pytest.TempPathFactory) -> Path:
        # TASK-670: run the adapter install ONCE for this class's read-only
        # assertions instead of per test. The mutating test (disabled-skills)
        # keeps the per-test `project` fixture so it never corrupts this shared
        # scaffold — a fresh mktemp dir also keeps the two fully isolated.
        project = tmp_path_factory.mktemp("claude-adapter") / "myproject"
        project.mkdir()
        result = run_adapter_install("claude", project)
        assert result.returncode == 0, f"Install failed: {result.stderr}"
        return project

    def test_install_succeeds(self, installed: Path) -> None:
        assert (installed / ".claude").is_dir()

    def test_creates_claude_dir(self, installed: Path) -> None:
        assert (installed / ".claude").is_dir()

    def test_symlinks_hooks(self, installed: Path) -> None:
        hooks_dir = installed / ".claude" / "hooks"
        assert hooks_dir.is_dir()
        hook_files = list(hooks_dir.glob("*.sh"))
        adapter_private_dir = ADAPTERS_DIR / "claude" / "hooks"
        # Adapter-private hooks overlay core ones on name clash (D4), so the
        # installed set is core ∪ adapter-private, not a plain sum.
        core_names = {p.name for p in CORE_HOOKS_DIR.glob("*.sh")}
        adapter_private = {p.name for p in adapter_private_dir.glob("*.sh")}
        assert len(hook_files) == len(core_names | adapter_private)
        # Verify they are symlinks pointing to core or the adapter-private layer
        for hook in hook_files:
            assert hook.is_symlink()
            resolved = str(hook.resolve())
            assert str(CORE_HOOKS_DIR) in resolved or str(adapter_private_dir) in resolved

    def test_symlinks_rules(self, installed: Path) -> None:
        rules_dir = installed / ".claude" / "rules"
        rule_files = list(rules_dir.glob("*.md"))
        core_rule_count = len(
            [p for p in CORE_RULES_DIR.glob("*.md") if p.name not in NON_ACTIVE_RULES]
        )
        assert len(rule_files) == core_rule_count
        for rule in rule_files:
            assert rule.is_symlink()
        # The derived matrices must NOT be linked as always-active rules (C1).
        for excluded in NON_ACTIVE_RULES:
            assert not (rules_dir / excluded).exists()

    def test_symlinks_skills(self, installed: Path) -> None:
        skills_dir = installed / ".claude" / "skills"
        skill_dirs = [d for d in skills_dir.iterdir() if d.is_dir()]
        core_skill_count = len(list(CORE_SKILLS_DIR.iterdir()))
        assert len(skill_dirs) == core_skill_count
        for skill_dir in skill_dirs:
            skill_md = skill_dir / "SKILL.md"
            assert skill_md.exists()
            assert skill_md.is_symlink()

    def test_disabled_skills_skip_and_unlink(self, project: Path) -> None:
        # First install links everything; adding a disabled_skills opt-out then
        # re-installing must skip AND remove the disabled skill. Single store:
        # .coding-os.yaml::disabled_skills (no separate skill-overrides.json).
        # MUTATES the project → keeps the per-test `project` fixture (never the
        # shared `installed` scaffold).
        run_adapter_install("claude", project)
        assert (project / ".claude" / "skills" / "redis" / "SKILL.md").exists()

        config = project / ".coding-os.yaml"
        config.write_text("disabled_skills:\n  - redis\n  - supabase\n", encoding="utf-8")
        result = run_adapter_install("claude", project)
        assert result.returncode == 0, result.stderr

        assert not (project / ".claude" / "skills" / "redis").exists()
        assert not (project / ".claude" / "skills" / "supabase").exists()
        assert (project / ".claude" / "skills" / "clean-code" / "SKILL.md").exists()

    def test_generates_settings_json(self, installed: Path) -> None:
        settings = installed / ".claude" / "settings.json"
        assert settings.exists()
        data = json.loads(settings.read_text())
        assert "hooks" in data

    def test_settings_references_correct_hooks_dir(self, installed: Path) -> None:
        settings = installed / ".claude" / "settings.json"
        content = settings.read_text()
        assert ".claude/hooks" in content
        # No unresolved template placeholders
        assert "{{HOOKS_DIR}}" not in content

    def test_creates_mcp_json(self, installed: Path) -> None:
        mcp_json = installed / ".mcp.json"
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
