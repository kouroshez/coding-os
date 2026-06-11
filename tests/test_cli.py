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
        db_path = project_dir / ".coding-os" / "coding-os.db"
        assert db_path.exists()
        assert db_path.stat().st_size > 0

    def test_creates_scaffold_files(self, runner: CliRunner, project_dir: Path) -> None:
        project_dir.mkdir()
        runner.invoke(cli, ["init", "--agent", "claude", "-d", str(project_dir)])
        # Scrumban replaced the flat docs/tasks.md index (governance/docs-system.md);
        # canonical task state lives in docs/tasks/ + the board DB. Assert the
        # docs root exists and changes.log is seeded.
        assert (project_dir / "docs").is_dir()
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

    def test_creates_gitignore(self, runner: CliRunner, project_dir: Path) -> None:
        project_dir.mkdir()
        result = runner.invoke(cli, ["init", "--agent", "claude", "-d", str(project_dir)])
        assert result.exit_code == 0
        gitignore = project_dir / ".gitignore"
        assert gitignore.exists()
        body = gitignore.read_text()
        # runtime state ignored, tracked config carved back in
        assert ".coding-os/*" in body
        assert "*.db" in body
        assert "!.coding-os/rag-config.yaml" in body

    def test_baseline_commit_excludes_runtime_db(
        self, runner: CliRunner, project_dir: Path
    ) -> None:
        import subprocess

        project_dir.mkdir()
        result = runner.invoke(cli, ["init", "--agent", "claude", "-d", str(project_dir)])
        assert result.exit_code == 0
        if not (project_dir / ".git").exists():
            pytest.skip("tmp nested in an existing git repo — init skipped git init")
        log = subprocess.run(
            ["git", "-C", str(project_dir), "log", "--oneline"],
            capture_output=True,
            text=True,
        )
        assert log.returncode == 0
        assert len(log.stdout.strip().splitlines()) == 1  # exactly one baseline commit
        tracked = subprocess.run(
            ["git", "-C", str(project_dir), "ls-files"],
            capture_output=True,
            text=True,
        ).stdout
        assert ".gitignore" in tracked
        assert "coding-os.db" not in tracked  # mutating runtime DB never committed
        assert ".coding-os/rag-config.yaml" in tracked  # config IS versioned

    def test_installs_consumer_git_hooks(self, runner: CliRunner, project_dir: Path) -> None:
        project_dir.mkdir()
        result = runner.invoke(cli, ["init", "--agent", "claude", "-d", str(project_dir)])
        assert result.exit_code == 0
        if not (project_dir / ".git").exists():
            pytest.skip("tmp nested in an existing git repo — init skipped git init")
        pre = project_dir / ".git" / "hooks" / "pre-commit"
        msg = project_dir / ".git" / "hooks" / "commit-msg"
        assert pre.exists() and (pre.stat().st_mode & 0o111)  # executable
        assert msg.exists()
        # commit-msg body resolves the consumer's adapter hooks dir
        assert ".claude" in msg.read_text()

    def test_claude_adapter_creates_settings(self, runner: CliRunner, project_dir: Path) -> None:
        project_dir.mkdir()
        runner.invoke(cli, ["init", "--agent", "claude", "-d", str(project_dir)])
        assert (project_dir / ".claude" / "settings.json").exists()

    def test_claude_adapter_symlinks_hooks(self, runner: CliRunner, project_dir: Path) -> None:
        project_dir.mkdir()
        runner.invoke(cli, ["init", "--agent", "claude", "-d", str(project_dir)])
        hooks_dir = project_dir / ".claude" / "hooks"
        assert hooks_dir.is_dir()
        hook_files = list(hooks_dir.glob("*.sh"))
        assert len(hook_files) >= 15  # At least 15 hooks should be symlinked

    def test_claude_adapter_symlinks_rules(self, runner: CliRunner, project_dir: Path) -> None:
        project_dir.mkdir()
        runner.invoke(cli, ["init", "--agent", "claude", "-d", str(project_dir)])
        rules_dir = project_dir / ".claude" / "rules"
        assert rules_dir.is_dir()
        rule_files = list(rules_dir.glob("*.md"))
        assert len(rule_files) >= 1

    def test_claude_adapter_symlinks_skills(self, runner: CliRunner, project_dir: Path) -> None:
        project_dir.mkdir()
        runner.invoke(cli, ["init", "--agent", "claude", "-d", str(project_dir)])
        skills_dir = project_dir / ".claude" / "skills"
        assert skills_dir.is_dir()
        # Each skill should have a SKILL.md
        skill_mds = list(skills_dir.glob("*/SKILL.md"))
        assert len(skill_mds) >= 4  # clean-code, thinking_os, codebase-explorer, worktree

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
        result = runner.invoke(cli, ["add-adapter", "codex", "-d", str(initialized_project)])
        assert result.exit_code == 0
        assert (initialized_project / ".codex" / "hooks.json").exists()

    def test_updates_config(self, runner: CliRunner, initialized_project: Path) -> None:
        runner.invoke(cli, ["add-adapter", "codex", "-d", str(initialized_project)])
        import yaml

        config = yaml.safe_load((initialized_project / ".coding-os.yaml").read_text())
        assert "claude" in config["agents"]
        assert "codex" in config["agents"]

    def test_duplicate_adapter_noop(self, runner: CliRunner, initialized_project: Path) -> None:
        result = runner.invoke(cli, ["add-adapter", "claude", "-d", str(initialized_project)])
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

        result = runner.invoke(cli, ["add-adapter", "codex", "-d", str(initialized_project)])
        assert result.exit_code == 0
        assert agents_md.exists(), "add-adapter must generate missing AGENTS.md"
        assert "Generated AGENTS.md" in result.output

    def test_preserves_existing_agents_md(
        self, runner: CliRunner, initialized_project: Path
    ) -> None:
        agents_md = initialized_project / "AGENTS.md"
        sentinel = "## CUSTOM SECTION — do not overwrite\n"
        agents_md.write_text(sentinel)

        result = runner.invoke(cli, ["add-adapter", "codex", "-d", str(initialized_project)])
        assert result.exit_code == 0
        assert agents_md.read_text() == sentinel, (
            "add-adapter must not overwrite existing AGENTS.md"
        )


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
        result = runner.invoke(cli, ["codex-mcp-install", "--dry-run", "--config", str(target)])
        assert result.exit_code == 0
        assert "[mcp_servers.coding-os]" in result.output
        assert not target.exists(), "dry-run must not write"

    def test_writes_to_fresh_config(self, runner: CliRunner, tmp_path: Path) -> None:
        target = tmp_path / "codex" / "config.toml"
        result = runner.invoke(cli, ["codex-mcp-install", "--config", str(target)])
        assert result.exit_code == 0
        assert target.exists()
        content = target.read_text()
        assert "[mcp_servers.coding-os]" in content

    def test_preserves_existing_content(self, runner: CliRunner, tmp_path: Path) -> None:
        target = tmp_path / "config.toml"
        prior = '[mcp_servers.other]\ncommand = "other-tool"\n'
        target.write_text(prior)

        result = runner.invoke(cli, ["codex-mcp-install", "--config", str(target)])
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
        assert target.stat().st_size == size_after_first, (
            "second run must not append a duplicate section"
        )

    def test_repairs_existing_stale_entry(self, runner: CliRunner, tmp_path: Path) -> None:
        target = tmp_path / "config.toml"
        target.write_text(
            "[mcp_servers.coding-os]\n"
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

    def test_rejects_config_and_global_together(self, runner: CliRunner, tmp_path: Path) -> None:
        target = tmp_path / "config.toml"
        result = runner.invoke(cli, ["codex-mcp-install", "--config", str(target), "--global"])
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
            str(main_module.CORE_DIR / "thinking_os" / "server.py"),
        ]
        env = captured["env"]
        assert isinstance(env, dict)
        assert env["COS_DB_PATH"] == str(tmp_path / ".coding-os" / "coding-os.db")
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

    def test_health_shows_agent(self, runner: CliRunner, initialized_project: Path) -> None:
        result = runner.invoke(cli, ["health", "-d", str(initialized_project)])
        assert "claude" in result.output

    def test_health_shows_database(self, runner: CliRunner, initialized_project: Path) -> None:
        result = runner.invoke(cli, ["health", "-d", str(initialized_project)])
        assert "Database" in result.output

    def test_health_shows_hooks(self, runner: CliRunner, initialized_project: Path) -> None:
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
    def test_converts_symlinks_to_files(self, runner: CliRunner, initialized_project: Path) -> None:
        # Verify there are symlinks first
        symlink_count = sum(1 for f in initialized_project.rglob("*") if f.is_symlink())
        assert symlink_count > 0, "Init should create symlinks"

        result = runner.invoke(cli, ["eject", "-d", str(initialized_project)])
        assert result.exit_code == 0
        assert "Ejected" in result.output

        # Verify no symlinks remain
        remaining_symlinks = sum(1 for f in initialized_project.rglob("*") if f.is_symlink())
        assert remaining_symlinks == 0

    def test_ejected_files_have_content(self, runner: CliRunner, initialized_project: Path) -> None:
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
        assert "src/core/hooks" in result.output


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

pytestmark = pytest.mark.slow  # dominated by cos-init / subprocess tests


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

    def test_dot_uses_shell_pwd_when_available(self, tmp_path: Path, monkeypatch) -> None:
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

    def test_dot_falls_back_to_cwd_when_pwd_missing(self, tmp_path: Path, monkeypatch) -> None:
        """If $PWD is unset, fall back to os.getcwd() (legacy behavior)."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("PWD", raising=False)
        result = _resolve_project_dir(".")
        assert result == tmp_path.resolve()

    def test_dot_falls_back_when_pwd_is_invalid(self, tmp_path: Path, monkeypatch) -> None:
        """If $PWD points to a non-existent dir, fall back to os.getcwd()."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("PWD", "/definitely/does/not/exist/anywhere")
        result = _resolve_project_dir(".")
        assert result == tmp_path.resolve()


class TestRefuseSelfInit:
    """The CLI must refuse to init inside the coding-os source tree."""

    def test_refuses_coding_os_repo(self, tmp_path: Path) -> None:
        """A directory containing core/thinking_os/server.py AND cli/main.py
        is the coding-os repo itself — init should sys.exit(1)."""
        (tmp_path / "src" / "core" / "thinking_os").mkdir(parents=True)
        (tmp_path / "src" / "core" / "thinking_os" / "server.py").write_text("# fake")
        (tmp_path / "src" / "cli").mkdir(parents=True, exist_ok=True)
        (tmp_path / "src" / "cli" / "main.py").write_text("# fake")

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
        core/thinking_os/server.py is fine — only both together trigger
        the refuse."""
        (tmp_path / "src" / "cli").mkdir(parents=True, exist_ok=True)
        (tmp_path / "src" / "cli" / "main.py").write_text("# user's own cli")
        _refuse_coding_os_self_init(tmp_path)

    def test_init_refuses_self_init_end_to_end(self, runner: CliRunner, tmp_path: Path) -> None:
        """Full CLI invocation with a simulated coding-os repo should fail."""
        (tmp_path / "src" / "core" / "thinking_os").mkdir(parents=True)
        (tmp_path / "src" / "core" / "thinking_os" / "server.py").write_text("# fake")
        (tmp_path / "src" / "cli").mkdir(parents=True, exist_ok=True)
        (tmp_path / "src" / "cli" / "main.py").write_text("# fake")

        result = runner.invoke(cli, ["init", "--agent", "claude", "-d", str(tmp_path), "--force"])
        assert result.exit_code == 1
        assert "Refusing to init inside the coding-os repo" in result.output
        # And the fake source files must still exist — self-init check must
        # have fired BEFORE the --force wipe.
        assert (tmp_path / "src" / "core" / "thinking_os" / "server.py").exists()


# ---------------------------------------------------------------------------
# install resilience — TASK-346 (meta-repo relocation, version skew, hints)
# ---------------------------------------------------------------------------


class TestInstallResilience:
    @pytest.fixture(scope="class")
    def resilience_project(self, tmp_path_factory: pytest.TempPathFactory) -> Path:
        """One shared consumer project — init is the expensive step."""
        project = tmp_path_factory.mktemp("resilience") / "consumer"
        project.mkdir()
        result = CliRunner().invoke(
            cli,
            ["init", "--agent", "claude", "-d", str(project), "--no-index", "--no-register"],
        )
        assert result.exit_code == 0, f"init failed: {result.output}"
        return project

    def test_update_and_sync_roots_resolve_via_resources(self) -> None:
        """update/sync_all must use the importlib-resolved trees (TASK-219),
        not Path(__file__) hops that break under wheels / moved checkouts."""
        from cli._resources import data_root
        import cli.sync_all as sync_module
        import cli.update as update_module

        root = data_root()
        assert update_module.CORE_DIR == root / "core"
        assert update_module.ADAPTERS_DIR == root / "adapters"
        assert update_module.TEMPLATES_DIR == root / "templates"
        assert sync_module.CORE_DIR == root / "core"
        assert sync_module.ADAPTERS_DIR == root / "adapters"

    def test_update_warns_on_core_version_skew_and_restamps(
        self, runner: CliRunner, resilience_project: Path
    ) -> None:
        import json

        stamp = resilience_project / ".coding-os" / "core-version.json"
        stamp.write_text(
            json.dumps({"core_version": "0.0.1", "stamped_at": "2020-01-01T00:00:00+00:00"})
        )
        result = runner.invoke(cli, ["update", "-d", str(resilience_project)])
        assert result.exit_code == 0, result.output
        assert "core drift" in result.output
        assert "0.0.1" in result.output
        assert json.loads(stamp.read_text())["core_version"] != "0.0.1"

    def test_update_heals_dangling_symlinks(
        self, runner: CliRunner, resilience_project: Path
    ) -> None:
        """Top-level orphans go via diff removal; nested skill links are
        invisible to _scan_project_assets (SKILL.md.exists() is False on a
        dangling link) and only the leftover-prune pass heals them."""
        ghost_target = resilience_project / ".coding-os" / "ghost-target.sh"
        top_level = resilience_project / ".claude" / "hooks" / "zz-ghost-hook.sh"
        top_level.symlink_to(ghost_target)
        nested_skill_dir = resilience_project / ".claude" / "skills" / "zz-ghost-skill"
        nested_skill_dir.mkdir(parents=True)
        nested = nested_skill_dir / "SKILL.md"
        nested.symlink_to(ghost_target)
        assert top_level.is_symlink() and not top_level.exists()
        assert nested.is_symlink() and not nested.exists()

        result = runner.invoke(cli, ["update", "-d", str(resilience_project)])
        assert result.exit_code == 0, result.output
        assert not top_level.is_symlink()
        assert "Pruned" in result.output
        assert not nested.is_symlink()

    def test_any_command_nudges_on_dangling_links(
        self,
        runner: CliRunner,
        resilience_project: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The group-level probe fires for any command run inside the project."""
        dangling = resilience_project / ".claude" / "rules" / "zz-ghost-rule.md"
        dangling.symlink_to(resilience_project / "missing-rule.md")
        monkeypatch.chdir(resilience_project)

        result = runner.invoke(cli, ["update", "-d", str(resilience_project), "--dry-run"])
        assert "cos sync-doctor --repair" in result.output
        dangling.unlink()

    def test_registry_failure_prints_recovery_hint(
        self,
        runner: CliRunner,
        project_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import cli.registry as registry_module

        def _raise_disk_full(_project: Path):
            raise OSError("disk full")

        monkeypatch.setattr(registry_module, "add_project", _raise_disk_full)
        project_dir.mkdir()
        result = runner.invoke(
            cli, ["init", "--agent", "claude", "-d", str(project_dir), "--no-index"]
        )
        assert result.exit_code == 0, result.output
        assert "cos registry add" in result.output

    def test_db_init_failure_prints_recovery_hint(
        self,
        runner: CliRunner,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import subprocess

        real_run = subprocess.run

        def _fail_init_db(args, **kwargs):
            if isinstance(args, list) and any("init_db" in str(arg) for arg in args):
                return subprocess.CompletedProcess(args, 1, stdout="", stderr="boom")
            return real_run(args, **kwargs)

        monkeypatch.setattr(main_module.subprocess, "run", _fail_init_db)
        project = tmp_path / "dbfail"
        project.mkdir()
        result = runner.invoke(
            cli, ["init", "--agent", "claude", "-d", str(project), "--no-index", "--no-register"]
        )
        assert result.exit_code != 0
        assert "uv sync --extra rag" in result.output


# ---------------------------------------------------------------------------
# language layer — TASK-348 (language field, extends, plain stacks)
# ---------------------------------------------------------------------------


class TestLanguageLayer:
    def _registry(self):
        from cli._resources import templates_dir
        from cli.stack_registry import load_stack_registry

        return load_stack_registry(templates_dir())

    def test_every_stack_declares_language_and_validates(self) -> None:
        result = self._registry()
        assert list(result.warnings) == []
        for stack_id in result.keys():
            assert result[stack_id].language, f"{stack_id} missing language"

    def test_discovery_groups_by_language(self) -> None:
        from cli.stack_registry import group_stacks_by_language

        result = self._registry()
        profiles = {sid: result[sid] for sid in result.keys()}
        groups = group_stacks_by_language(profiles)
        go_ids = [p.id for p in groups["go"]]
        assert "go-plain" in go_ids and "go-fiber" in go_ids

    def test_bare_language_resolves_to_plain_stack_deterministically(self) -> None:
        from cli.stack_registry import plain_stack_by_language

        result = self._registry()
        profiles = {sid: result[sid] for sid in result.keys()}
        plain = plain_stack_by_language(profiles)
        assert plain["go"] == "go-plain"  # explicit -plain wins over the chi 'go' stack
        assert plain["python"] == "python"  # pre-convention fallback
        assert plain["typescript"] == "typescript-plain"

    @staticmethod
    def _write_stack(root: Path, stack_id: str, body: str) -> None:
        d = root / stack_id
        d.mkdir()
        (d / "stack.yaml").write_text(body, encoding="utf-8")

    def test_extends_merges_parent_substitutions(self, tmp_path: Path) -> None:
        from cli.stack_registry import load_stack_registry

        self._write_stack(
            tmp_path,
            "parent",
            "version: 1\nid: parent\nlanguage: go\nlabel: P\ncategory: library\n"
            "substitutions: {A: from-parent, B: from-parent}\nskills: [s-parent]\n",
        )
        self._write_stack(
            tmp_path,
            "child",
            "version: 1\nid: child\nlanguage: go\nlabel: C\ncategory: library\n"
            "extends: parent\nsubstitutions: {B: from-child}\nskills: [s-child]\n",
        )
        result = load_stack_registry(tmp_path)
        child = result["child"]
        assert child.substitutions == {"A": "from-parent", "B": "from-child"}
        assert child.skills == ("s-parent", "s-child")

    def test_extends_cycle_skips_with_warning(self, tmp_path: Path) -> None:
        from cli.stack_registry import load_stack_registry

        self._write_stack(
            tmp_path,
            "alpha",
            "version: 1\nid: alpha\nlanguage: go\nlabel: A\ncategory: library\nextends: beta\n",
        )
        self._write_stack(
            tmp_path,
            "beta",
            "version: 1\nid: beta\nlanguage: go\nlabel: B\ncategory: library\nextends: alpha\n",
        )
        result = load_stack_registry(tmp_path)
        assert "alpha" not in result.keys() and "beta" not in result.keys()
        assert any("cycle" in w for w in result.warnings)

    def test_plain_stacks_scaffold_runnable_skeletons(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        project = tmp_path / "plainproj"
        project.mkdir()
        result = runner.invoke(
            cli,
            [
                "init",
                "--agent",
                "claude",
                "-d",
                str(project),
                "--template",
                "go-plain",
                "--template",
                "typescript-plain",
                "--no-index",
                "--no-register",
            ],
        )
        assert result.exit_code == 0, result.output
        go_mod = project / "src" / "backend" / "go.mod"
        assert go_mod.exists()
        assert "module plainproj" in go_mod.read_text()
        assert (project / "tsconfig.json").exists()
        index_ts = project / "src" / "index.ts"
        assert index_ts.exists()
        assert "{{PROJECT_NAME}}" not in index_ts.read_text()


# ---------------------------------------------------------------------------
# project anatomy — TASK-351 (structure spec + multi-backend relocation)
# ---------------------------------------------------------------------------


class TestProjectAnatomy:
    def test_every_stack_declares_structure_root(self) -> None:
        from cli._resources import templates_dir
        from cli.stack_registry import load_stack_registry

        result = load_stack_registry(templates_dir())
        for stack_id in result.keys():
            structure = result[stack_id].structure
            assert structure.get("root"), f"{stack_id} missing structure.root"
            assert structure.get("tree"), f"{stack_id} missing structure.tree"

    def test_colliding_roots_compute_service_relocations(self) -> None:
        relocations = main_module._service_relocations(("go-plain", "go-fiber"))
        assert relocations == {
            "go-plain": "src/services/go-plain",
            "go-fiber": "src/services/go-fiber",
        }
        # Single owner → untouched.
        assert main_module._service_relocations(("go-plain", "nextjs")) == {}

    def test_multi_backend_init_relocates_to_services(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        project = tmp_path / "twoback"
        project.mkdir()
        result = runner.invoke(
            cli,
            [
                "init",
                "--agent",
                "claude",
                "-d",
                str(project),
                "--template",
                "go-plain",
                "--template",
                "go-fiber",
                "--no-index",
                "--no-register",
            ],
        )
        assert result.exit_code == 0, result.output
        relocated = project / "src" / "services" / "go-plain" / "go.mod"
        assert relocated.exists()
        assert "module twoback" in relocated.read_text()
        assert not (project / "src" / "backend" / "go.mod").exists()


# ---------------------------------------------------------------------------
# Regen-chain parameterization — TASK-355 (service-scoped glob propagation)
# ---------------------------------------------------------------------------


class TestRegenChainRelocation:
    """project-anatomy.md § Glob/verify propagation for relocated services."""

    @pytest.fixture(scope="class")
    def composed_world(self):
        return main_module._build_world(
            "claude", ("go-fiber", "fastapi"), Path("/virtual/twosvc")
        )

    @pytest.fixture(scope="class")
    def composed_project(self, tmp_path_factory: pytest.TempPathFactory) -> Path:
        """One shared two-backend consumer — init is the expensive step."""
        project = tmp_path_factory.mktemp("regen-chain") / "twosvc"
        project.mkdir()
        result = CliRunner().invoke(
            cli,
            [
                "init",
                "--agent",
                "claude",
                "-d",
                str(project),
                "--template",
                "go-fiber",
                "--template",
                "fastapi",
                "--no-index",
                "--no-register",
            ],
        )
        assert result.exit_code == 0, f"init failed: {result.output}"
        return project

    def test_registry_tables_are_service_scoped(self, composed_world) -> None:
        from cli.renderer import render_dimension_registry, render_skill_enforcement

        enforcement = render_skill_enforcement(composed_world)
        assert "`src/services/fastapi/**/*.py`" in enforcement
        assert "`src/services/go-fiber/**/*.go`" in enforcement
        assert "src/backend" not in enforcement
        registry = render_dimension_registry(composed_world)
        assert "## fastapi" in registry and "## go-fiber" in registry

    def test_single_stack_world_passthrough(self) -> None:
        """Backward compatibility: no collision → emitted globs unchanged."""
        from cli.renderer import render_skill_enforcement

        world = main_module._build_world("claude", ("fastapi",), Path("/virtual/solo"))
        enforcement = render_skill_enforcement(world)
        assert "`src/backend/**/*.py`" in enforcement
        assert "src/services/" not in enforcement
        names = [t.name for t in world.makefile_targets]
        assert "lint-backend" in names
        assert not any(n.endswith("-fastapi") for n in names)
        assert world.substitutions["VERIFY_BACKEND_SUITES"] == "lint-backend + test-backend"

    def test_makefile_targets_do_not_dedupe_collide(self, composed_world) -> None:
        """Both stacks declare lint-backend/test-backend; unsuffixed names
        would dedupe-by-name and silently drop one stack's suite."""
        cmds = {t.name: t.cmd for t in composed_world.makefile_targets}
        assert "lint-backend-go-fiber" in cmds and "lint-backend-fastapi" in cmds
        assert "test-backend-go-fiber" in cmds and "test-backend-fastapi" in cmds
        assert "lint-backend" not in cmds and "test-backend" not in cmds
        assert "src/services/fastapi" in cmds["lint-backend-fastapi"]
        assert "src/services/go-fiber" in cmds["test-backend-go-fiber"]

    def test_verify_substitutions_join_both_services(self, composed_world) -> None:
        substitutions = composed_world.substitutions
        assert "src/services/go-fiber" in substitutions["VERIFY_BACKEND_GLOB"]
        assert "src/services/fastapi" in substitutions["VERIFY_BACKEND_GLOB"]
        assert "lint-backend-go-fiber" in substitutions["VERIFY_BACKEND_SUITES"]
        assert "lint-backend-fastapi" in substitutions["VERIFY_BACKEND_SUITES"]

    def test_init_artifacts_service_scoped(self, composed_project: Path) -> None:
        import yaml

        agents_md = (composed_project / "AGENTS.md").read_text(encoding="utf-8")
        assert "src/services/go-fiber" in agents_md
        assert "src/services/fastapi" in agents_md
        # Stack makefile targets are not materialized into the consumer
        # Makefile by init (pre-existing gap, all stacks — TASK-392); the
        # renamed suites reach the consumer through AGENTS.md text.
        assert "lint-backend-go-fiber" in agents_md
        assert "lint-backend-fastapi" in agents_md

        boundary = yaml.safe_load(
            (composed_project / ".coding-os" / "scaffold-boundary.yaml").read_text(
                encoding="utf-8"
            )
        )
        forbids = {e["stack"]: e["forbids_writing_in"] for e in boundary["stacks"]}
        assert "src/services/fastapi/" in forbids["go-fiber"]
        assert "src/services/go-fiber/" in forbids["fastapi"]
        assert "src/services/go-fiber/" not in forbids["go-fiber"]

    def test_cross_service_write_blocked_by_boundary_delegate(
        self, composed_project: Path
    ) -> None:
        """Acceptance: a write crossing another service's subtree is flagged
        using the parameterized boundary data (exit 2 from the delegate)."""
        import subprocess

        repo_root = Path(__file__).resolve().parent.parent
        delegate = repo_root / "src" / "core" / "hooks" / "_enforce_scaffold_boundary.py"
        boundary_file = composed_project / ".coding-os" / "scaffold-boundary.yaml"

        def _verdict(rel_path: str) -> int:
            return subprocess.run(
                [sys.executable, str(delegate), str(boundary_file), rel_path, str(composed_project)],
                capture_output=True,
                timeout=10,
            ).returncode

        # Unowned cross-service write (a .go file inside the fastapi service).
        assert _verdict("src/services/fastapi/rogue.go") == 2
        # Owned writes inside each service stay allowed.
        assert _verdict("src/services/fastapi/app/api.py") == 0
        assert _verdict("src/services/go-fiber/internal/handler.go") == 0

    def test_skill_primer_remaps_relocated_globs(self, composed_project: Path) -> None:
        import importlib.util

        repo_root = Path(__file__).resolve().parent.parent
        helper = repo_root / "src" / "core" / "hooks" / "_helpers" / "skill_primer.py"
        spec = importlib.util.spec_from_file_location("skill_primer_t355", helper)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        stacks = [
            (stack_id, module._load_stack(repo_root, stack_id))
            for stack_id in ("go-fiber", "fastapi")
        ]
        state_dir = composed_project / ".coding-os"
        overrides = module._service_root_overrides(state_dir, stacks)
        assert overrides == {
            "go-fiber": ("src/backend", "src/services/go-fiber"),
            "fastapi": ("src/backend", "src/services/fastapi"),
        }
        card = module._format_card(stacks, overrides)
        assert "src/services/go-fiber/**/*.go" in card
        assert "src/services/fastapi/**/*.py" in card
        assert "src/backend" not in card


# ---------------------------------------------------------------------------
# Presets + dry-config — TASK-356 (config-composition.md § Presets)
# ---------------------------------------------------------------------------


class TestPresets:
    def test_init_with_preset_scaffolds_declared_composition(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        import yaml

        project = tmp_path / "from-preset"
        project.mkdir()
        result = runner.invoke(
            cli,
            [
                "init",
                "--agent",
                "claude",
                "-d",
                str(project),
                "--preset",
                "nextjs-fastapi",
                "--yes",
                "--no-index",
                "--no-register",
            ],
        )
        assert result.exit_code == 0, result.output
        assert "Preset 'nextjs-fastapi'" in result.output
        config = yaml.safe_load((project / ".coding-os.yaml").read_text(encoding="utf-8"))
        assert config["templates"] == ["nextjs", "fastapi"]
        assert config["preset"] == "nextjs-fastapi"

    def test_preset_and_template_are_mutually_exclusive(self, runner: CliRunner) -> None:
        result = runner.invoke(
            cli,
            ["init", "--agent", "claude", "--preset", "nextjs-fastapi", "--template", "go", "--yes"],
        )
        assert result.exit_code == 2
        assert "mutually exclusive" in result.output

    def test_unknown_preset_errors_listing_available(self, runner: CliRunner) -> None:
        result = runner.invoke(
            cli, ["init", "--agent", "claude", "--preset", "no-such-preset", "--yes"]
        )
        assert result.exit_code == 2
        assert "no-such-preset" in result.output
        assert "nextjs-fastapi" in result.output  # available presets listed

    def test_dry_config_previews_union_and_conflicts_without_writing(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("PWD", str(tmp_path))
        result = runner.invoke(
            cli,
            ["init", "--template", "go-fiber", "--template", "fastapi", "--dry-config", "--yes"],
        )
        assert result.exit_code == 0, result.output
        assert "Merge preview for stacks: go-fiber, fastapi" in result.output
        assert "swimlanes:" in result.output and "handlers" in result.output
        assert "conflicts (" in result.output and "later wins" in result.output
        assert "nothing written" in result.output
        assert list(tmp_path.iterdir()) == []  # zero filesystem effects

    def test_dry_config_json_shape(self, runner: CliRunner, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("PWD", str(tmp_path))
        result = runner.invoke(
            cli, ["init", "--template", "nextjs", "--dry-config", "--yes", "--format", "json"]
        )
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["stacks"] == ["nextjs"]
        assert "scrumban-config.yaml" in payload["configs"]
        assert payload["conflicts"] == []  # single stack never conflicts

    def test_list_stacks_shows_presets(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["list-stacks", "--format", "json"])
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        by_id = {p["id"]: p for p in payload["presets"]}
        assert by_id["nextjs-fastapi"]["stacks"] == ["nextjs", "fastapi"]
        text = runner.invoke(cli, ["list-stacks"])
        assert "Presets (cos init --preset <id>):" in text.output


# ---------------------------------------------------------------------------
# doctor --bootstrap — TASK-347 (preflight prerequisite checks)
# ---------------------------------------------------------------------------


class TestDoctorBootstrap:
    _ALL_CHECK_IDS = (
        "bootstrap.python_version",
        "bootstrap.bash_version",
        "bootstrap.git_present",
        "bootstrap.uv_present",
        "bootstrap.sed_flavor",
    )

    def test_all_checks_pass_on_dev_machine(self, runner: CliRunner) -> None:
        """Runs with NO project — a brand-new user's very first command."""
        result = runner.invoke(cli, ["doctor", "--bootstrap"])
        assert result.exit_code == 0, result.output
        for check_id in self._ALL_CHECK_IDS:
            assert check_id in result.output

    def test_old_bash_fails_with_brew_hint(
        self, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import cli.doctor as doctor_module

        real_capture = doctor_module._capture_tool_version

        def _bash_32(executable: str):
            if executable == "bash":
                return "GNU bash, version 3.2.57(1)-release (arm64-apple-darwin24)"
            return real_capture(executable)

        monkeypatch.setattr(doctor_module, "_capture_tool_version", _bash_32)
        result = runner.invoke(cli, ["doctor", "--bootstrap"])
        assert result.exit_code == 1
        assert "brew install bash" in result.output

    def test_missing_git_fails_with_install_hint(
        self, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import cli.doctor as doctor_module

        real_capture = doctor_module._capture_tool_version
        monkeypatch.setattr(
            doctor_module,
            "_capture_tool_version",
            lambda exe: None if exe == "git" else real_capture(exe),
        )
        result = runner.invoke(cli, ["doctor", "--bootstrap"])
        assert result.exit_code == 1
        assert "git not found" in result.output

    def test_missing_uv_warns_but_passes_unless_strict(
        self, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import cli.doctor as doctor_module

        real_capture = doctor_module._capture_tool_version
        monkeypatch.setattr(
            doctor_module,
            "_capture_tool_version",
            lambda exe: None if exe == "uv" else real_capture(exe),
        )
        result = runner.invoke(cli, ["doctor", "--bootstrap"])
        assert result.exit_code == 0, result.output
        assert "uv not found" in result.output

        strict_result = runner.invoke(cli, ["doctor", "--bootstrap", "--strict"])
        assert strict_result.exit_code == 1

    def test_json_format_is_machine_readable(self, runner: CliRunner) -> None:
        import json

        result = runner.invoke(cli, ["doctor", "--bootstrap", "--format", "json"])
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        reported_ids = {check["id"] for check in payload["checks"]}
        assert set(self._ALL_CHECK_IDS) <= reported_ids
