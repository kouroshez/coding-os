"""
Tests for cli/main.py — init, add-adapter, health, eject commands.

Covers:
  - init creates state dir, config, database, scaffold files, Makefile, AGENTS.md
  - add-adapter adds second adapter, updates config
  - health reports status correctly
  - eject converts symlinks to real files
  - hooks-dir prints core hooks path
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

# Ensure cli module is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cli.main as main_module
from cli.main import cli


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    """Return a clean temporary project directory."""
    return tmp_path / "test-project"


@pytest.fixture
def initialized_project(runner: CliRunner, project_dir: Path) -> Path:
    """Return a project directory after running init."""
    project_dir.mkdir()
    result = runner.invoke(cli, ["init", "--agent", "claude", "-d", str(project_dir)])
    assert result.exit_code == 0, f"init failed: {result.output}"
    return project_dir


# ---------------------------------------------------------------------------
# init command
# ---------------------------------------------------------------------------


class TestInit:
    def test_creates_state_directory(self, runner: CliRunner, project_dir: Path) -> None:
        project_dir.mkdir()
        result = runner.invoke(cli, ["init", "--agent", "claude", "-d", str(project_dir)])
        assert result.exit_code == 0
        assert (project_dir / ".coding-os").is_dir()

    def test_creates_config_file(self, runner: CliRunner, project_dir: Path) -> None:
        project_dir.mkdir()
        runner.invoke(cli, ["init", "--agent", "claude", "-d", str(project_dir)])
        config_path = project_dir / ".coding-os.yaml"
        assert config_path.exists()

    def test_config_contains_agent(self, runner: CliRunner, project_dir: Path) -> None:
        project_dir.mkdir()
        runner.invoke(cli, ["init", "--agent", "claude", "-d", str(project_dir)])
        import yaml

        config = yaml.safe_load((project_dir / ".coding-os.yaml").read_text())
        assert "claude" in config["agents"]

    def test_initializes_database(self, runner: CliRunner, project_dir: Path) -> None:
        project_dir.mkdir()
        runner.invoke(cli, ["init", "--agent", "claude", "-d", str(project_dir)])
        db_path = project_dir / ".coding-os" / "thinking-os.db"
        assert db_path.exists()
        assert db_path.stat().st_size > 0

    def test_creates_scaffold_files(self, runner: CliRunner, project_dir: Path) -> None:
        project_dir.mkdir()
        runner.invoke(cli, ["init", "--agent", "claude", "-d", str(project_dir)])
        assert (project_dir / "docs" / "tasks.md").exists()
        assert (project_dir / "changes.log").exists()

    def test_creates_makefile(self, runner: CliRunner, project_dir: Path) -> None:
        project_dir.mkdir()
        runner.invoke(cli, ["init", "--agent", "claude", "-d", str(project_dir)])
        makefile = project_dir / "Makefile"
        assert makefile.exists()
        content = makefile.read_text()
        assert "include .coding-os/Makefile.base" in content

    def test_creates_agents_md(self, runner: CliRunner, project_dir: Path) -> None:
        project_dir.mkdir()
        runner.invoke(cli, ["init", "--agent", "claude", "-d", str(project_dir)])
        agents_md = project_dir / "AGENTS.md"
        assert agents_md.exists()

    def test_claude_adapter_creates_settings(
        self, runner: CliRunner, project_dir: Path
    ) -> None:
        project_dir.mkdir()
        runner.invoke(cli, ["init", "--agent", "claude", "-d", str(project_dir)])
        assert (project_dir / ".claude" / "settings.json").exists()

    def test_claude_adapter_symlinks_hooks(
        self, runner: CliRunner, project_dir: Path
    ) -> None:
        project_dir.mkdir()
        runner.invoke(cli, ["init", "--agent", "claude", "-d", str(project_dir)])
        hooks_dir = project_dir / ".claude" / "hooks"
        assert hooks_dir.is_dir()
        hook_files = list(hooks_dir.glob("*.sh"))
        assert len(hook_files) >= 15  # At least 15 hooks should be symlinked

    def test_claude_adapter_symlinks_rules(
        self, runner: CliRunner, project_dir: Path
    ) -> None:
        project_dir.mkdir()
        runner.invoke(cli, ["init", "--agent", "claude", "-d", str(project_dir)])
        rules_dir = project_dir / ".claude" / "rules"
        assert rules_dir.is_dir()
        rule_files = list(rules_dir.glob("*.md"))
        assert len(rule_files) >= 1

    def test_claude_adapter_symlinks_skills(
        self, runner: CliRunner, project_dir: Path
    ) -> None:
        project_dir.mkdir()
        runner.invoke(cli, ["init", "--agent", "claude", "-d", str(project_dir)])
        skills_dir = project_dir / ".claude" / "skills"
        assert skills_dir.is_dir()
        # Each skill should have a SKILL.md
        skill_mds = list(skills_dir.glob("*/SKILL.md"))
        assert len(skill_mds) >= 4  # clean-code, thinking-os, codebase-explorer, worktree

    def test_creates_mcp_json(self, runner: CliRunner, project_dir: Path) -> None:
        project_dir.mkdir()
        runner.invoke(cli, ["init", "--agent", "claude", "-d", str(project_dir)])
        mcp_json = project_dir / ".mcp.json"
        assert mcp_json.exists()
        data = json.loads(mcp_json.read_text())
        assert "coding-os" in data.get("mcpServers", {})

    def test_init_with_template(self, runner: CliRunner, project_dir: Path) -> None:
        project_dir.mkdir()
        result = runner.invoke(
            cli, ["init", "--agent", "claude", "-t", "django", "-d", str(project_dir)]
        )
        assert result.exit_code == 0
        assert "django" in result.output.lower() or "Template" in result.output

    def test_init_codex(self, runner: CliRunner, project_dir: Path) -> None:
        project_dir.mkdir()
        result = runner.invoke(cli, ["init", "--agent", "codex", "-d", str(project_dir)])
        assert result.exit_code == 0
        assert (project_dir / ".codex" / "hooks.json").exists()

    def test_idempotent_init(self, runner: CliRunner, project_dir: Path) -> None:
        """Running init twice requires --force on the second run (non-empty target)."""
        project_dir.mkdir()
        runner.invoke(cli, ["init", "--agent", "claude", "-d", str(project_dir)])
        result = runner.invoke(
            cli, ["init", "--agent", "claude", "-d", str(project_dir), "--force"]
        )
        assert result.exit_code == 0

    def test_does_not_overwrite_existing_scaffold(
        self, runner: CliRunner, project_dir: Path
    ) -> None:
        """Init should not overwrite existing scaffold files."""
        project_dir.mkdir()
        tasks_dir = project_dir / "docs"
        tasks_dir.mkdir(parents=True)
        tasks_file = tasks_dir / "tasks.md"
        tasks_file.write_text("# My existing tasks\n")
        runner.invoke(cli, ["init", "--agent", "claude", "-d", str(project_dir)])
        assert tasks_file.read_text() == "# My existing tasks\n"


# ---------------------------------------------------------------------------
# add-adapter command
# ---------------------------------------------------------------------------


class TestAddAdapter:
    def test_adds_codex_to_claude_project(
        self, runner: CliRunner, initialized_project: Path
    ) -> None:
        result = runner.invoke(
            cli, ["add-adapter", "codex", "-d", str(initialized_project)]
        )
        assert result.exit_code == 0
        assert (initialized_project / ".codex" / "hooks.json").exists()

    def test_updates_config(
        self, runner: CliRunner, initialized_project: Path
    ) -> None:
        runner.invoke(
            cli, ["add-adapter", "codex", "-d", str(initialized_project)]
        )
        import yaml

        config = yaml.safe_load(
            (initialized_project / ".coding-os.yaml").read_text()
        )
        assert "claude" in config["agents"]
        assert "codex" in config["agents"]

    def test_duplicate_adapter_noop(
        self, runner: CliRunner, initialized_project: Path
    ) -> None:
        result = runner.invoke(
            cli, ["add-adapter", "claude", "-d", str(initialized_project)]
        )
        assert result.exit_code == 0
        assert "already installed" in result.output

    def test_fails_without_init(self, runner: CliRunner, tmp_path: Path) -> None:
        result = runner.invoke(cli, ["add-adapter", "codex", "-d", str(tmp_path)])
        assert result.exit_code != 0

    def test_generates_agents_md_if_missing(
        self, runner: CliRunner, initialized_project: Path
    ) -> None:
        # Simulate a partial install where AGENTS.md was never generated.
        agents_md = initialized_project / "AGENTS.md"
        if agents_md.exists():
            agents_md.unlink()

        result = runner.invoke(
            cli, ["add-adapter", "codex", "-d", str(initialized_project)]
        )
        assert result.exit_code == 0
        assert agents_md.exists(), "add-adapter must generate missing AGENTS.md"
        assert "Generated AGENTS.md" in result.output

    def test_preserves_existing_agents_md(
        self, runner: CliRunner, initialized_project: Path
    ) -> None:
        agents_md = initialized_project / "AGENTS.md"
        sentinel = "## CUSTOM SECTION — do not overwrite\n"
        agents_md.write_text(sentinel)

        result = runner.invoke(
            cli, ["add-adapter", "codex", "-d", str(initialized_project)]
        )
        assert result.exit_code == 0
        assert agents_md.read_text() == sentinel, \
            "add-adapter must not overwrite existing AGENTS.md"


# ---------------------------------------------------------------------------
# codex-mcp-install command
# ---------------------------------------------------------------------------


class TestCodexMcpInstall:
    def test_default_writes_project_local_config(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(cli, ["codex-mcp-install"])
        assert result.exit_code == 0
        target = tmp_path / ".codex" / "config.toml"
        assert target.exists()
        assert "[mcp_servers.coding-os]" in target.read_text(encoding="utf-8")

    def test_dry_run_prints_snippet(self, runner: CliRunner, tmp_path: Path) -> None:
        target = tmp_path / "fake-codex-config.toml"
        result = runner.invoke(
            cli, ["codex-mcp-install", "--dry-run", "--config", str(target)]
        )
        assert result.exit_code == 0
        assert "[mcp_servers.coding-os]" in result.output
        assert not target.exists(), "dry-run must not write"

    def test_writes_to_fresh_config(self, runner: CliRunner, tmp_path: Path) -> None:
        target = tmp_path / "codex" / "config.toml"
        result = runner.invoke(
            cli, ["codex-mcp-install", "--config", str(target)]
        )
        assert result.exit_code == 0
        assert target.exists()
        content = target.read_text()
        assert "[mcp_servers.coding-os]" in content

    def test_preserves_existing_content(self, runner: CliRunner, tmp_path: Path) -> None:
        target = tmp_path / "config.toml"
        prior = '[mcp_servers.other]\ncommand = "other-tool"\n'
        target.write_text(prior)

        result = runner.invoke(
            cli, ["codex-mcp-install", "--config", str(target)]
        )
        assert result.exit_code == 0
        new = target.read_text()
        assert prior in new, "existing MCP entries must survive"
        assert "[mcp_servers.coding-os]" in new

    def test_idempotent(self, runner: CliRunner, tmp_path: Path) -> None:
        target = tmp_path / "config.toml"
        runner.invoke(cli, ["codex-mcp-install", "--config", str(target)])
        size_after_first = target.stat().st_size

        result = runner.invoke(cli, ["codex-mcp-install", "--config", str(target)])
        assert result.exit_code == 0
        assert "Already registered" in result.output
        assert target.stat().st_size == size_after_first, \
            "second run must not append a duplicate section"

    def test_repairs_existing_stale_entry(self, runner: CliRunner, tmp_path: Path) -> None:
        target = tmp_path / "config.toml"
        target.write_text(
            '[mcp_servers.coding-os]\n'
            'command = "uv"\n'
            'args = ["run", "--directory", "/old/path", "python", "server.py"]\n',
            encoding="utf-8",
        )

        result = runner.invoke(cli, ["codex-mcp-install", "--config", str(target)])
        assert result.exit_code == 0
        content = target.read_text(encoding="utf-8")
        assert content.count("[mcp_servers.coding-os]") == 1
        assert "/old/path" not in content
        assert 'command = "uv"' not in content

    def test_fallback_uses_python_not_uv(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        target = tmp_path / "config.toml"

        def fake_which(name: str) -> str | None:
            return None if name == "cos" else shutil.which(name)

        monkeypatch.setattr(main_module.shutil, "which", fake_which)
        result = runner.invoke(cli, ["codex-mcp-install", "--config", str(target)])
        assert result.exit_code == 0
        content = target.read_text(encoding="utf-8")
        assert 'command = "uv"' not in content
        assert sys.executable in content

    def test_rejects_config_and_global_together(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        target = tmp_path / "config.toml"
        result = runner.invoke(
            cli, ["codex-mcp-install", "--config", str(target), "--global"]
        )
        assert result.exit_code != 0
        assert "either --config or --global" in result.output


class TestServerStart:
    def test_execs_current_python_directly(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict[str, object] = {}

        def fake_execvpe(file: str, args: list[str], env: dict[str, str]) -> None:
            captured["file"] = file
            captured["args"] = args
            captured["env"] = env
            raise SystemExit(0)

        monkeypatch.setattr(main_module.os, "execvpe", fake_execvpe)
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(cli, ["server-start"])

        assert result.exit_code == 0, result.output
        assert captured["file"] == sys.executable
        assert captured["args"] == [
            sys.executable,
            str(main_module.CORE_DIR / "thinking-os" / "server.py"),
        ]
        env = captured["env"]
        assert isinstance(env, dict)
        assert env["COS_DB_PATH"] == str(tmp_path / ".coding-os" / "thinking-os.db")
        assert env["COS_STATE_DIR"] == str(tmp_path / ".coding-os")


# ---------------------------------------------------------------------------
# health command
# ---------------------------------------------------------------------------


class TestHealth:
    def test_health_on_initialized_project(
        self, runner: CliRunner, initialized_project: Path
    ) -> None:
        result = runner.invoke(cli, ["health", "-d", str(initialized_project)])
        assert result.exit_code == 0
        assert "OK" in result.output

    def test_health_shows_agent(
        self, runner: CliRunner, initialized_project: Path
    ) -> None:
        result = runner.invoke(cli, ["health", "-d", str(initialized_project)])
        assert "claude" in result.output

    def test_health_shows_database(
        self, runner: CliRunner, initialized_project: Path
    ) -> None:
        result = runner.invoke(cli, ["health", "-d", str(initialized_project)])
        assert "Database" in result.output

    def test_health_shows_hooks(
        self, runner: CliRunner, initialized_project: Path
    ) -> None:
        result = runner.invoke(cli, ["health", "-d", str(initialized_project)])
        assert "hooks" in result.output.lower()

    def test_health_missing_config(self, runner: CliRunner, tmp_path: Path) -> None:
        result = runner.invoke(cli, ["health", "-d", str(tmp_path)])
        assert result.exit_code == 0
        assert "MISSING" in result.output


# ---------------------------------------------------------------------------
# eject command
# ---------------------------------------------------------------------------


class TestEject:
    def test_converts_symlinks_to_files(
        self, runner: CliRunner, initialized_project: Path
    ) -> None:
        # Verify there are symlinks first
        symlink_count = sum(
            1
            for f in initialized_project.rglob("*")
            if f.is_symlink()
        )
        assert symlink_count > 0, "Init should create symlinks"

        result = runner.invoke(cli, ["eject", "-d", str(initialized_project)])
        assert result.exit_code == 0
        assert "Ejected" in result.output

        # Verify no symlinks remain
        remaining_symlinks = sum(
            1
            for f in initialized_project.rglob("*")
            if f.is_symlink()
        )
        assert remaining_symlinks == 0

    def test_ejected_files_have_content(
        self, runner: CliRunner, initialized_project: Path
    ) -> None:
        runner.invoke(cli, ["eject", "-d", str(initialized_project)])
        # After eject, settings.json should still be readable
        settings = initialized_project / ".claude" / "settings.json"
        assert settings.exists()
        assert settings.stat().st_size > 0


# ---------------------------------------------------------------------------
# hooks-dir command
# ---------------------------------------------------------------------------


class TestHooksDir:
    def test_prints_hooks_path(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["hooks-dir"])
        assert result.exit_code == 0
        assert "core/hooks" in result.output


# ---------------------------------------------------------------------------
# version
# ---------------------------------------------------------------------------


class TestVersion:
    def test_version(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        # Any semver string is fine; just confirm version line rendered.
        assert "version" in result.output.lower()


# ---------------------------------------------------------------------------
# Regression: --project-dir resolution under `uv run --directory`
# ---------------------------------------------------------------------------
#
# Bug caught by end-to-end usage: when `uv run --directory /path/to/coding-os`
# changes cwd before launching Python, `Path(".").resolve()` resolves to the
# coding-os repo itself — silently scattering scaffold files into the repo.
#
# The fix reads `$PWD` from the environment (shells preserve it across cd)
# and refuses to init when the target directory looks like the coding-os
# repo itself.

from cli.main import _refuse_coding_os_self_init, _resolve_project_dir  # noqa: E402


class TestResolveProjectDir:
    def test_explicit_absolute_path(self, tmp_path: Path) -> None:
        """Explicit absolute paths are returned as-is (resolved)."""
        result = _resolve_project_dir(str(tmp_path))
        assert result == tmp_path.resolve()

    def test_explicit_relative_path(self, tmp_path: Path, monkeypatch) -> None:
        """Explicit relative paths resolve against Python cwd."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "subdir").mkdir()
        result = _resolve_project_dir("subdir")
        assert result == (tmp_path / "subdir").resolve()

    def test_dot_uses_shell_pwd_when_available(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """When raw=='.' and $PWD is set, use $PWD instead of os.getcwd()."""
        real_project = tmp_path / "real-project"
        real_project.mkdir()
        fake_cwd = tmp_path / "fake-uv-cwd"
        fake_cwd.mkdir()

        monkeypatch.chdir(fake_cwd)
        monkeypatch.setenv("PWD", str(real_project))

        result = _resolve_project_dir(".")
        assert result == real_project.resolve()
        # Must NOT be the fake Python cwd
        assert result != fake_cwd.resolve()

    def test_dot_falls_back_to_cwd_when_pwd_missing(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """If $PWD is unset, fall back to os.getcwd() (legacy behavior)."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("PWD", raising=False)
        result = _resolve_project_dir(".")
        assert result == tmp_path.resolve()

    def test_dot_falls_back_when_pwd_is_invalid(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """If $PWD points to a non-existent dir, fall back to os.getcwd()."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("PWD", "/definitely/does/not/exist/anywhere")
        result = _resolve_project_dir(".")
        assert result == tmp_path.resolve()


class TestRefuseSelfInit:
    """The CLI must refuse to init inside the coding-os source tree."""

    def test_refuses_coding_os_repo(self, tmp_path: Path) -> None:
        """A directory containing core/thinking-os/server.py AND cli/main.py
        is the coding-os repo itself — init should sys.exit(1)."""
        (tmp_path / "core" / "thinking-os").mkdir(parents=True)
        (tmp_path / "core" / "thinking-os" / "server.py").write_text("# fake")
        (tmp_path / "cli").mkdir()
        (tmp_path / "cli" / "main.py").write_text("# fake")

        with pytest.raises(SystemExit) as exc_info:
            _refuse_coding_os_self_init(tmp_path)
        assert exc_info.value.code == 1

    def test_allows_normal_project(self, tmp_path: Path) -> None:
        """A regular project without those files should pass through."""
        (tmp_path / "src").mkdir()
        (tmp_path / "README.md").write_text("# My project")
        # Should not raise
        _refuse_coding_os_self_init(tmp_path)

    def test_allows_project_with_only_cli_main(self, tmp_path: Path) -> None:
        """A project that happens to have cli/main.py but NOT
        core/thinking-os/server.py is fine — only both together trigger
        the refuse."""
        (tmp_path / "cli").mkdir()
        (tmp_path / "cli" / "main.py").write_text("# user's own cli")
        _refuse_coding_os_self_init(tmp_path)

    def test_init_refuses_self_init_end_to_end(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """Full CLI invocation with a simulated coding-os repo should fail."""
        (tmp_path / "core" / "thinking-os").mkdir(parents=True)
        (tmp_path / "core" / "thinking-os" / "server.py").write_text("# fake")
        (tmp_path / "cli").mkdir()
        (tmp_path / "cli" / "main.py").write_text("# fake")

        result = runner.invoke(
            cli, ["init", "--agent", "claude", "-d", str(tmp_path), "--force"]
        )
        assert result.exit_code == 1
        assert "Refusing to init inside the coding-os repo" in result.output
        # And the fake source files must still exist — self-init check must
        # have fired BEFORE the --force wipe.
        assert (tmp_path / "core" / "thinking-os" / "server.py").exists()
