"""Part of tests/test_cli.py — collected via the aggregator, not directly."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from click.testing import CliRunner

from _cli_suite.shared import (
    _class_scaffold_cli,
    _claude_entrypoint_name,
    cli,
)

# ---------------------------------------------------------------------------
# init command
# ---------------------------------------------------------------------------
from cli.main import _refuse_coding_os_self_init, _resolve_project_dir


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
