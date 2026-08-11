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
        assert (hooks_dir / "codex-preedit-dispatch.sh").exists()
        assert (hooks_dir / "codex-postedit-dispatch.sh").exists()
        assert (hooks_dir / "codex-sessionstart-dispatch.sh").exists()
        assert (hooks_dir / "codex-sessionend-dispatch.sh").exists()
        assert (hooks_dir / "codex-stop-dispatch.sh").exists()
        assert (hooks_dir / "codex-normalize-edit.py").is_symlink()
        assert (hooks_dir / "codex-merge-hook-output.py").is_symlink()

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

        session_end = data["hooks"]["SessionEnd"][0]["hooks"]
        assert len(session_end) == 1
        assert "codex-sessionend-dispatch.sh" in session_end[0]["command"]
        assert session_end[0]["command"].startswith("env COS_AGENT=codex ")
        assert session_end[0]["timeout"] == 3

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
        assert "hooks = true" in content
        assert "[shell_environment_policy.set]" in content
        assert 'COS_AGENT = "codex"' in content
        assert str(project / ".coding-os") in content
        assert str(project / ".coding-os" / "codex") in content

    def test_codex_mcp_receives_adapter_owned_identity(self, project: Path) -> None:
        run_adapter_install("codex", project)
        content = (project / ".codex" / "config.toml").read_text(encoding="utf-8")
        mcp_section = content.split("[mcp_servers.coding-os]", 1)[1]

        assert 'COS_AGENT = "codex"' in mcp_section
        assert f'COS_STATE_DIR = "{project / ".coding-os"}"' in mcp_section
        assert f'COS_AGENT_DIR = "{project / ".coding-os" / "codex"}"' in mcp_section

    def test_codex_config_preserves_unrelated_shell_environment_values(self, project: Path) -> None:
        codex_cfg = project / ".codex" / "config.toml"
        codex_cfg.parent.mkdir(parents=True, exist_ok=True)
        codex_cfg.write_text(
            '[shell_environment_policy.set]\nKEEP_ME = "yes"\nCOS_AGENT = "stale"\n',
            encoding="utf-8",
        )

        run_adapter_install("codex", project)

        content = codex_cfg.read_text(encoding="utf-8")
        assert 'KEEP_ME = "yes"' in content
        assert content.count('COS_AGENT = "codex"') == 2
        assert 'COS_AGENT = "stale"' not in content

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
        assert codex_cfg.read_text().count("hooks = true") == 1
        assert codex_cfg.read_text().count("[shell_environment_policy.set]") == 1
        assert "codex_hooks" not in codex_cfg.read_text()

    def test_installed_hooks_assert_codex_identity_without_runtime_markers(
        self, project: Path
    ) -> None:
        run_adapter_install("codex", project)
        (project / ".coding-os" / ".agent").write_text("claude\n", encoding="utf-8")
        data = json.loads((project / ".codex" / "hooks.json").read_text(encoding="utf-8"))
        command = data["hooks"]["SessionStart"][0]["hooks"][0]["command"]
        blocked = {
            "COS_AGENT",
            "COS_AGENT_DIR",
            "CODEX_SESSION_ID",
            "CODEX_AGENT_DIR",
            "CODEX_HOME",
            "CLAUDECODE",
            "CLAUDE_CODE_SSE_PORT",
            "CLAUDE_CODE_ENTRYPOINT",
            "CLAUDE_AGENT_SDK_VERSION",
            "CLAUDE_PROJECT_DIR",
        }
        env = {k: v for k, v in os.environ.items() if k not in blocked}
        result = subprocess.run(
            ["/bin/sh", "-c", command],
            input=json.dumps(
                {
                    "session_id": "codex-desktop-test",
                    "hook_event_name": "SessionStart",
                    "source": "startup",
                    "cwd": str(project),
                }
            ),
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(project),
            env=env,
        )

        assert result.returncode == 0, result.stderr
        assert any((project / ".coding-os" / "codex" / "sessions").glob("*.json"))
        assert not (project / ".coding-os" / "claude" / "sessions").exists()

    def test_repairs_false_hooks_without_corrupting_next_section(self, project: Path) -> None:
        codex_cfg = project / ".codex" / "config.toml"
        codex_cfg.parent.mkdir(parents=True, exist_ok=True)
        codex_cfg.write_text(
            "[features]\n"
            "codex_hooks = false\n\n"
            "rmcp_client = true\n"
            "[mcp_servers.coding-os]\n"
            'command = "cos"\n'
            'args = ["server-start"]\n',
            encoding="utf-8",
        )

        run_adapter_install("codex", project)

        content = codex_cfg.read_text(encoding="utf-8")
        assert "hooks = true\n\n[mcp_servers.coding-os]" in content
        assert "codex_hooks" not in content
        assert "rmcp_client" not in content
        assert content.count("[mcp_servers.coding-os]") == 1

    def test_repairs_stale_mcp_entry_in_place(self, project: Path) -> None:
        codex_cfg = project / ".codex" / "config.toml"
        codex_cfg.parent.mkdir(parents=True, exist_ok=True)
        codex_cfg.write_text(
            "[features]\n"
            "hooks = true\n\n"
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
        source_rules = {p.name for p in CORE_RULES_DIR.glob("*.md")} - NON_ACTIVE_RULES
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
