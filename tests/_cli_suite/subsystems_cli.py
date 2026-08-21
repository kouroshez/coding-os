"""cos subsystems — the module CLI, its lifecycle, and supervision configuration.

Part of tests/test_cli.py — collected via the aggregator, not directly.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from _cli_suite.shared import (
    cli,
)


class TestSupervisionCli:
    def _project(self, tmp_path: Path) -> Path:
        project = tmp_path / "supervision-project"
        (project / ".coding-os").mkdir(parents=True)
        (project / ".coding-os.yaml").write_text(
            "version: 1\nagents: [claude, codex]\ntemplates: []\n", encoding="utf-8"
        )
        return project

    def test_show_deep_normalizes_legacy_policy(self, runner: CliRunner, tmp_path: Path) -> None:
        project = self._project(tmp_path)
        (project / ".coding-os" / "hub-settings.json").write_text(
            '{"model_routing":{"enabled":false}}', encoding="utf-8"
        )

        result = runner.invoke(
            cli,
            ["supervision", "show", "-d", str(project), "--format", "json"],
        )

        assert result.exit_code == 0, result.output
        policy = json.loads(result.output)["policy"]
        assert policy["cooldown"] == {"default_seconds": 300, "maximum_seconds": 3600}
        assert policy["orchestrator"] == {"adapter": "", "model": "", "effort": ""}

    def test_enable_configure_disable_preserves_other_settings(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        project = self._project(tmp_path)
        path = project / ".coding-os" / "hub-settings.json"
        path.write_text('{"foreign":{"keep":true}}', encoding="utf-8")

        enabled = runner.invoke(cli, ["supervision", "enable", "-d", str(project)])
        configured = runner.invoke(
            cli,
            [
                "supervision",
                "set",
                "-d",
                str(project),
                "--mode",
                "adaptive",
                "--fallback-policy",
                "next_eligible",
                "--cooldown-default-seconds",
                "90",
                "--role",
                "reviewer",
                "--role-adapter",
                "codex",
                # codex declares a model catalog, so the id must be one it
                # published; it declares no effort_selection, so an effort here
                # would be rejected outright.
                "--role-model",
                "gpt-5.6-sol",
            ],
        )
        disabled = runner.invoke(cli, ["supervision", "disable", "-d", str(project)])

        assert enabled.exit_code == 0, enabled.output
        assert configured.exit_code == 0, configured.output
        assert disabled.exit_code == 0, disabled.output
        stored = json.loads(path.read_text(encoding="utf-8"))
        assert stored["foreign"] == {"keep": True}
        assert stored["model_routing"]["enabled"] is False
        assert stored["model_routing"]["mode"] == "adaptive"
        assert stored["model_routing"]["roles"]["reviewer"]["adapter"] == "codex"

    def test_set_rejects_a_target_dispatch_could_never_satisfy(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        project = self._project(tmp_path)

        for args, expected in (
            (["--role", "reviewer", "--role-adapter", "ghost"], "unknown adapter"),
            (
                ["--role", "reviewer", "--role-adapter", "codex", "--role-effort", "high"],
                "not supported",
            ),
            (
                ["--role", "reviewer", "--role-adapter", "claude", "--role-model", "not-a-model"],
                "not declared",
            ),
        ):
            result = runner.invoke(cli, ["supervision", "set", "-d", str(project), *args])

            assert result.exit_code != 0, result.output
            assert expected in result.output

    def test_set_rejects_inverted_cooldown(self, runner: CliRunner, tmp_path: Path) -> None:
        project = self._project(tmp_path)

        result = runner.invoke(
            cli,
            [
                "supervision",
                "set",
                "-d",
                str(project),
                "--cooldown-default-seconds",
                "600",
                "--cooldown-maximum-seconds",
                "300",
            ],
        )

        assert result.exit_code != 0
        assert "maximum_seconds must be greater" in result.output


class TestModuleCli:
    def _init(self, runner: CliRunner, tmp_path: Path) -> Path:
        project = tmp_path / "modproj"
        project.mkdir()
        result = runner.invoke(
            cli,
            [
                "init",
                "--agent",
                "claude",
                # all modules on — these tests assert the disable/enable round-trip
                # against a clean baseline, which the default `standard` profile
                # (cognition off) would pollute with cognition's disabled hooks.
                "--profile",
                "full",
                "-d",
                str(project),
                "--yes",
                "--no-index",
                "--no-register",
            ],
        )
        assert result.exit_code == 0, result.output
        return project

    def test_list_shows_kernel_locked_and_dependencies(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = self._init(runner, tmp_path)
        monkeypatch.chdir(project)
        result = runner.invoke(cli, ["module", "list"])
        assert result.exit_code == 0, result.output
        assert "kernel (always on)" in result.output
        assert "needs: docs" in result.output  # tasks → docs dependency surfaced

    def test_disable_refusal_propagates_dependency_chain(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = self._init(runner, tmp_path)
        monkeypatch.chdir(project)
        result = runner.invoke(cli, ["module", "disable", "docs"])
        assert result.exit_code != 0
        assert "required by enabled module(s) tasks" in result.output

    def test_disable_regenerates_agents_md_and_allowlist(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = self._init(runner, tmp_path)
        monkeypatch.chdir(project)
        baseline = (project / "AGENTS.md").read_text(encoding="utf-8")
        assert "Scrumban board" in baseline

        result = runner.invoke(cli, ["module", "disable", "tasks"])
        assert result.exit_code == 0, result.output
        regenerated = (project / "AGENTS.md").read_text(encoding="utf-8")
        assert "Scrumban board" not in regenerated
        assert (project / "AGENTS.md.bak").exists()  # diff-safe backup
        allowlist = project / ".coding-os" / "disabled-hook-scripts"
        assert allowlist.exists()
        assert "auto-task-sync" in allowlist.read_text(encoding="utf-8")

        restore = runner.invoke(cli, ["module", "enable", "tasks"])
        assert restore.exit_code == 0, restore.output
        assert (project / "AGENTS.md").read_text(encoding="utf-8") == baseline
        assert allowlist.read_text(encoding="utf-8").strip() == ""

    def test_outside_project_fails_fast(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(cli, ["module", "list"])
        assert result.exit_code != 0
        assert "not a coding-os project" in result.output


class TestModuleLifecycle:
    def _init(self, runner: CliRunner, tmp_path: Path) -> Path:
        project = tmp_path / "lifeproj"
        project.mkdir()
        result = runner.invoke(
            cli,
            [
                "init",
                "--agent",
                "claude",
                # all modules on — test_update_migrates asserts the pre-module
                # shape (no subsystems-state.json), which the default `standard`
                # profile would break by writing state for its disabled modules.
                "--profile",
                "full",
                "-d",
                str(project),
                "--yes",
                "--no-index",
                "--no-register",
            ],
        )
        assert result.exit_code == 0, result.output
        return project

    def test_disable_reenable_preserves_all_task_data(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = self._init(runner, tmp_path)
        monkeypatch.chdir(project)
        tasks_dir = project / "docs" / "tasks"
        tasks_dir.mkdir(parents=True, exist_ok=True)
        seeded = {}
        for i in (1, 2, 3):
            f = tasks_dir / f"TASK-00{i}-seed.md"
            f.write_text(
                f"---\nid: TASK-00{i}\nstatus: icebox\n---\n# seed {i}\n", encoding="utf-8"
            )
            seeded[f.name] = f.read_text(encoding="utf-8")
        db = project / ".coding-os" / "coding-os.db"
        db_size_before = db.stat().st_size

        assert runner.invoke(cli, ["module", "disable", "tasks"]).exit_code == 0
        assert runner.invoke(cli, ["module", "enable", "tasks"]).exit_code == 0

        for name, content in seeded.items():
            assert (tasks_dir / name).read_text(encoding="utf-8") == content  # untouched
        assert db.exists() and db.stat().st_size == db_size_before  # no DB row purge

    def test_update_migrates_pre_module_consumer_with_zero_behavior_change(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        project = self._init(runner, tmp_path)
        state_file = project / ".coding-os" / "subsystems-state.json"
        assert not state_file.exists()  # lazy default — pre-module shape
        agents_before = (project / "AGENTS.md").read_text(encoding="utf-8")

        result = runner.invoke(cli, ["update", "-d", str(project)])
        assert result.exit_code == 0, result.output
        assert "Migrated to module registry" in result.output
        assert json.loads(state_file.read_text(encoding="utf-8")) == {
            "version": 1,
            "disabled": [],
        }
        assert (project / "AGENTS.md").read_text(encoding="utf-8") == agents_before

        rerun = runner.invoke(cli, ["update", "-d", str(project)])
        assert rerun.exit_code == 0
        assert "Migrated to module registry" not in rerun.output  # idempotent

    def test_regen_failure_rolls_back_module_state(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import cli.module_commands as module_commands

        project = self._init(runner, tmp_path)
        monkeypatch.chdir(project)

        def _boom(_project: Path) -> list[str]:
            raise OSError("disk full")

        monkeypatch.setattr(module_commands, "regen_after_toggle", _boom)
        result = runner.invoke(cli, ["module", "disable", "memory"])
        assert result.exit_code != 0
        assert "rolled back" in result.output

        from cli.subsystems import module_state

        assert module_state(project)["memory"] is True  # state flip reverted
