"""Part of tests/test_cli.py — collected via the aggregator, not directly."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

from _cli_suite.shared import (
    _class_scaffold_cli,
    _claude_entrypoint_name,
    cli,
    main_module,
)

# ---------------------------------------------------------------------------
# init command
# ---------------------------------------------------------------------------


class TestInit:
    # TASK-670: the read-only init-property assertions below share one class-scoped
    # `cos init` instead of one per test. Tests that need a *different* scaffold
    # (template / codex / re-init / pre-populated) keep their own per-test init.
    @pytest.fixture(scope="class")
    def initialized(self, tmp_path_factory: pytest.TempPathFactory) -> Path:
        return _class_scaffold_cli(tmp_path_factory, "cli-init")

    def test_creates_state_directory(self, initialized: Path) -> None:
        assert (initialized / ".coding-os").is_dir()

    def test_creates_config_file(self, initialized: Path) -> None:
        assert (initialized / ".coding-os.yaml").exists()

    def test_config_contains_agent(self, initialized: Path) -> None:
        import yaml

        config = yaml.safe_load((initialized / ".coding-os.yaml").read_text())
        assert "claude" in config["agents"]

    def test_initializes_database(self, initialized: Path) -> None:
        db_path = initialized / ".coding-os" / "coding-os.db"
        assert db_path.exists()
        assert db_path.stat().st_size > 0

    def test_creates_scaffold_files(self, initialized: Path) -> None:
        # Scrumban replaced the flat docs/tasks.md index (governance/docs-system.md);
        # canonical task state lives in docs/tasks/ + the board DB. Assert the
        # docs root exists and changes.log is seeded.
        assert (initialized / "docs").is_dir()
        assert (initialized / "changes.log").exists()

    def test_quickstart_swimlane_validates(self, initialized: Path) -> None:
        # The post-init quick start pastes a runnable `cos task-create`; a literal
        # swimlane there fails validation on every stack that overrides the base set.
        import yaml

        from cli.main import _example_swimlane

        config = yaml.safe_load((initialized / ".coding-os" / "scrumban-config.yaml").read_text())
        assert _example_swimlane(initialized) in {lane["id"] for lane in config["swimlanes"]}

    def test_creates_makefile(self, initialized: Path) -> None:
        makefile = initialized / "Makefile"
        assert makefile.exists()
        content = makefile.read_text()
        assert "include .coding-os/Makefile.base" in content

    def test_creates_agents_md(self, initialized: Path) -> None:
        assert (initialized / "AGENTS.md").exists()

    def test_links_adapter_entrypoint_at_agents_md(self, initialized: Path) -> None:
        # Claude Code reads CLAUDE.md, not AGENTS.md — init links the two so the
        # instruction SSOT can never fork. Relative, so the project stays movable.
        entrypoint = initialized / _claude_entrypoint_name()
        assert entrypoint.is_symlink()
        assert os.readlink(entrypoint) == "AGENTS.md"
        assert entrypoint.read_text(encoding="utf-8") == (initialized / "AGENTS.md").read_text(
            encoding="utf-8"
        )

    def test_creates_gitignore(self, initialized: Path) -> None:
        gitignore = initialized / ".gitignore"
        assert gitignore.exists()
        body = gitignore.read_text()
        # runtime state ignored, tracked config carved back in
        assert ".coding-os/*" in body
        assert "*.db" in body
        assert "!.coding-os/rag-config.yaml" in body

    def test_baseline_commit_excludes_runtime_db(self, initialized: Path) -> None:
        import subprocess

        if not (initialized / ".git").exists():
            pytest.skip("tmp nested in an existing git repo — init skipped git init")
        log = subprocess.run(
            ["git", "-C", str(initialized), "log", "--oneline"],
            capture_output=True,
            text=True,
        )
        assert log.returncode == 0
        assert len(log.stdout.strip().splitlines()) == 1  # exactly one baseline commit
        tracked = subprocess.run(
            ["git", "-C", str(initialized), "ls-files"],
            capture_output=True,
            text=True,
        ).stdout
        assert ".gitignore" in tracked
        assert "coding-os.db" not in tracked  # mutating runtime DB never committed
        assert ".coding-os/rag-config.yaml" in tracked  # config IS versioned

    def test_installs_consumer_git_hooks(self, initialized: Path) -> None:
        if not (initialized / ".git").exists():
            pytest.skip("tmp nested in an existing git repo — init skipped git init")
        pre = initialized / ".git" / "hooks" / "pre-commit"
        msg = initialized / ".git" / "hooks" / "commit-msg"
        assert pre.exists() and (pre.stat().st_mode & 0o111)  # executable
        assert msg.exists()
        # commit-msg body resolves the consumer's adapter hooks dir
        assert ".claude" in msg.read_text()

    def test_claude_adapter_creates_settings(self, initialized: Path) -> None:
        assert (initialized / ".claude" / "settings.json").exists()

    def test_claude_adapter_symlinks_hooks(self, initialized: Path) -> None:
        hooks_dir = initialized / ".claude" / "hooks"
        assert hooks_dir.is_dir()
        hook_files = list(hooks_dir.glob("*.sh"))
        assert len(hook_files) >= 15  # At least 15 hooks should be symlinked

    def test_claude_adapter_symlinks_rules(self, initialized: Path) -> None:
        rules_dir = initialized / ".claude" / "rules"
        assert rules_dir.is_dir()
        rule_files = list(rules_dir.glob("*.md"))
        assert len(rule_files) >= 1

    def test_claude_adapter_symlinks_skills(self, initialized: Path) -> None:
        skills_dir = initialized / ".claude" / "skills"
        assert skills_dir.is_dir()
        # Each skill should have a SKILL.md
        skill_mds = list(skills_dir.glob("*/SKILL.md"))
        assert len(skill_mds) >= 4  # clean-code, thinking_os, codebase-explorer, worktree

    def test_creates_mcp_json(self, initialized: Path) -> None:
        mcp_json = initialized / ".mcp.json"
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
# makefile materialization (TASK-392)
# ---------------------------------------------------------------------------


class TestMakefileMaterialization:
    def _init(self, runner: CliRunner, project_dir: Path, *templates: str) -> Path:
        project_dir.mkdir()
        args = [
            "init",
            "--agent",
            "claude",
            "-d",
            str(project_dir),
            "--no-index",
            "--no-register",
            "--no-git",
        ]
        for template in templates:
            args += ["--template", template]
        result = runner.invoke(cli, args)
        assert result.exit_code == 0, result.output
        return project_dir

    def test_single_backend_target_is_materialized(
        self, runner: CliRunner, project_dir: Path
    ) -> None:
        project = self._init(runner, project_dir, "fastapi")
        stacks = (project / ".coding-os" / "Makefile.stacks").read_text()
        assert "lint-backend:" in stacks
        assert "cd src/backend" in stacks
        makefile = (project / "Makefile").read_text()
        assert "-include .coding-os/Makefile.stacks" in makefile

    def test_multi_backend_targets_relocated_into_services(
        self, runner: CliRunner, project_dir: Path
    ) -> None:
        project = self._init(runner, project_dir, "fastapi", "go-fiber")
        stacks = (project / ".coding-os" / "Makefile.stacks").read_text()
        assert "lint-backend-fastapi:" in stacks
        assert "lint-backend-go-fiber:" in stacks
        assert "cd src/services/fastapi" in stacks
        assert "cd src/services/go-fiber" in stacks

    def test_update_wires_include_into_legacy_makefile(
        self, runner: CliRunner, project_dir: Path
    ) -> None:
        project = self._init(runner, project_dir, "fastapi")
        makefile = project / "Makefile"
        stacks = project / ".coding-os" / "Makefile.stacks"
        # simulate a pre-TASK-392 project: no stacks include, no generated file,
        # plus a user-authored target that must survive the update.
        makefile.write_text(
            "# Project Makefile\ninclude .coding-os/Makefile.base\n\nmy-target:\n\techo hi\n"
        )
        stacks.unlink()
        result = runner.invoke(cli, ["update", "-d", str(project), "--yes"])
        assert result.exit_code == 0, result.output
        text = makefile.read_text()
        assert "-include .coding-os/Makefile.stacks" in text  # include wired by update
        assert "my-target:" in text and "\techo hi" in text  # user target preserved
        assert "lint-backend:" in stacks.read_text()  # generated include restored


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

        monkeypatch.setattr(shutil, "which", fake_which)
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

        monkeypatch.setattr(os, "execvpe", fake_execvpe)
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
# materialize command (symlinks → standalone files)
# ---------------------------------------------------------------------------


class TestMaterialize:
    def test_converts_symlinks_to_files(self, runner: CliRunner, initialized_project: Path) -> None:
        # Verify there are symlinks first
        symlink_count = sum(1 for f in initialized_project.rglob("*") if f.is_symlink())
        assert symlink_count > 0, "Init should create symlinks"

        result = runner.invoke(cli, ["materialize", "-d", str(initialized_project)])
        assert result.exit_code == 0
        assert "Materialized" in result.output

        # Verify no symlinks remain
        remaining_symlinks = sum(1 for f in initialized_project.rglob("*") if f.is_symlink())
        assert remaining_symlinks == 0

    def test_materialized_files_have_content(
        self, runner: CliRunner, initialized_project: Path
    ) -> None:
        runner.invoke(cli, ["materialize", "-d", str(initialized_project)])
        # After materialize, settings.json should still be readable
        settings = initialized_project / ".claude" / "settings.json"
        assert settings.exists()
        assert settings.stat().st_size > 0


# ---------------------------------------------------------------------------
# eject command (remove coding-os, keep code/docs — TASK-388)
# ---------------------------------------------------------------------------


class TestEject:
    def test_eject_removes_coding_os_keeps_user_code(
        self, runner: CliRunner, initialized_project: Path
    ) -> None:
        user_file = initialized_project / "src" / "app.py"
        user_file.parent.mkdir(parents=True, exist_ok=True)
        user_file.write_text("print('user code')\n", encoding="utf-8")
        user_hash = hashlib.sha256(user_file.read_bytes()).hexdigest()
        assert sum(1 for f in initialized_project.rglob("*") if f.is_symlink()) > 0

        result = runner.invoke(cli, ["eject", "-d", str(initialized_project), "--yes"])
        assert result.exit_code == 0, result.output
        assert "Ejected coding-os" in result.output
        # coding-os wiring removed
        assert sum(1 for f in initialized_project.rglob("*") if f.is_symlink()) == 0
        assert not (initialized_project / ".coding-os").exists()
        assert not (initialized_project / ".coding-os.yaml").exists()
        assert not (initialized_project / "AGENTS.md").exists()
        # user code byte-identical
        assert hashlib.sha256(user_file.read_bytes()).hexdigest() == user_hash

    def test_eject_keeps_entrypoint_the_user_replaced_with_a_real_file(
        self, runner: CliRunner, initialized_project: Path
    ) -> None:
        entrypoint = initialized_project / _claude_entrypoint_name()
        entrypoint.unlink()
        entrypoint.write_text("my own instructions\n", encoding="utf-8")

        result = runner.invoke(cli, ["eject", "-d", str(initialized_project), "--yes"])
        assert result.exit_code == 0, result.output
        assert entrypoint.read_text(encoding="utf-8") == "my own instructions\n"

    def test_eject_idempotent_noop_on_clean_dir(self, runner: CliRunner, tmp_path: Path) -> None:
        result = runner.invoke(cli, ["eject", "-d", str(tmp_path), "--yes"])
        assert result.exit_code == 0, result.output
        assert "nothing to eject" in result.output.lower()


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


from cli.main import _refuse_coding_os_self_init, _resolve_project_dir


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
        import cli.sync_all as sync_module
        import cli.update as update_module
        from cli._resources import data_root

        root = data_root()
        assert root / "core" == update_module.CORE_DIR
        assert root / "adapters" == update_module.ADAPTERS_DIR
        assert root / "templates" == update_module.TEMPLATES_DIR
        assert root / "core" == sync_module.CORE_DIR
        assert root / "adapters" == sync_module.ADAPTERS_DIR

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

    def test_update_keeps_adapter_owned_hooks(self) -> None:
        """The diff must claim the adapter's own hooks, not just the core set.

        Treating them as unknown made `cos update` delete them — for Codex that
        is every dispatcher, i.e. its whole hook-parity mechanism.
        """
        from cli.update import ADAPTERS_DIR, _build_target_assets

        for agent in ("claude", "codex"):
            owned = ADAPTERS_DIR / agent / "hooks"
            if not owned.is_dir():
                continue
            expected = {
                path.name
                for path in owned.iterdir()
                if path.is_file() and path.suffix in (".sh", ".py")
            }
            assert expected, f"{agent} declares no adapter-owned hooks to guard"

            claimed = {ref.name for ref in _build_target_assets(agent, [])["hooks"]}

            assert expected <= claimed, sorted(expected - claimed)

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

        monkeypatch.setattr(subprocess, "run", _fail_init_db)
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
        for stack_id in result:
            assert result[stack_id].language, f"{stack_id} missing language"

    def test_discovery_groups_by_language(self) -> None:
        from cli.stack_registry import group_stacks_by_language

        result = self._registry()
        profiles = {sid: result[sid] for sid in result}
        groups = group_stacks_by_language(profiles)
        go_ids = [p.id for p in groups["go"]]
        assert "go-plain" in go_ids and "go-fiber" in go_ids

    def test_bare_language_resolves_to_plain_stack_deterministically(self) -> None:
        from cli.stack_registry import plain_stack_by_language

        result = self._registry()
        profiles = {sid: result[sid] for sid in result}
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
        assert "alpha" not in result and "beta" not in result
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
        # Quoted because the template must parse before substitution (TASK-890);
        # Go normalises it away on the project's first `go mod tidy`.
        assert 'module "plainproj"' in go_mod.read_text()
        assert (project / "tsconfig.json").exists()
        index_ts = project / "src" / "index.ts"
        assert index_ts.exists()
        assert "{{PROJECT_NAME}}" not in index_ts.read_text()


# ---------------------------------------------------------------------------
# project anatomy — TASK-351 (structure spec + multi-backend relocation)
# ---------------------------------------------------------------------------
