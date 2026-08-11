"""Part of tests/test_cli.py — collected via the aggregator, not directly."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from click.testing import CliRunner

from _cli_suite.shared import (
    cli,
)


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
            [
                "init",
                "--agent",
                "claude",
                "--preset",
                "nextjs-fastapi",
                "--template",
                "go",
                "--yes",
            ],
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

    def test_dry_run_previews_tree_without_writing(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("PWD", str(tmp_path))
        result = runner.invoke(
            cli,
            ["init", "--agent", "claude", "--template", "fastapi", "--dry-run", "--yes"],
        )
        assert result.exit_code == 0, result.output
        assert "Scaffold preview for stacks: fastapi" in result.output
        assert "file(s) would be created" in result.output
        assert "AGENTS.md" in result.output
        assert ".coding-os.yaml" in result.output
        assert "nothing written" in result.output
        assert list(tmp_path.iterdir()) == []  # zero filesystem effects

    def test_dry_run_with_preset_reflects_expansion(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("PWD", str(tmp_path))
        result = runner.invoke(
            cli,
            ["init", "--agent", "claude", "--preset", "nextjs-fastapi", "--dry-run", "--yes"],
        )
        assert result.exit_code == 0, result.output
        assert "Preset 'nextjs-fastapi' → stacks: nextjs, fastapi" in result.output
        assert "Scaffold preview for stacks: nextjs, fastapi" in result.output
        assert list(tmp_path.iterdir()) == []  # zero filesystem effects

    def test_dry_run_json_shape(self, runner: CliRunner, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("PWD", str(tmp_path))
        result = runner.invoke(
            cli,
            [
                "init",
                "--agent",
                "claude",
                "--template",
                "nextjs",
                "--dry-run",
                "--yes",
                "--format",
                "json",
            ],
        )
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["stacks"] == ["nextjs"]
        assert "AGENTS.md" in payload["files"]
        assert ".coding-os/scrumban-config.yaml" in payload["files"]
        assert payload["conflicts"] == []  # single stack never conflicts
        assert list(tmp_path.iterdir()) == []  # zero filesystem effects

    def test_list_stacks_shows_presets(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["list-stacks", "--format", "json"])
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        by_id = {p["id"]: p for p in payload["presets"]}
        assert by_id["nextjs-fastapi"]["stacks"] == ["nextjs", "fastapi"]
        text = runner.invoke(cli, ["list-stacks"])
        assert "Presets (cos init --preset <id>):" in text.output


class TestCliOnboardingParity:
    def test_skills_and_summary_flags_seed_project(self, runner: CliRunner, tmp_path: Path) -> None:
        import yaml

        project = tmp_path / "withextras"
        project.mkdir()
        result = runner.invoke(
            cli,
            [
                "init",
                "--agent",
                "claude",
                "-d",
                str(project),
                "--skills",
                "redis, docker",
                "--summary",
                "A focused product summary for the intake pipeline.",
                "--yes",
                "--no-index",
                "--no-register",
            ],
        )
        assert result.exit_code == 0, result.output
        cfg = yaml.safe_load((project / ".coding-os.yaml").read_text(encoding="utf-8"))
        assert cfg["extra_skills"] == ["redis", "docker"]
        intake = project / "docs" / "_meta" / "project-description.md"
        assert "focused product summary" in intake.read_text(encoding="utf-8")
        # A one-liner is not an authored PRD: the seed keeps _TODO: markers so
        # readiness stays a single signal (no second completion flag to sync).
        vision = project / "docs" / "prd" / "01-snapshot-vision.md"
        assert "_TODO:" in vision.read_text(encoding="utf-8")

    def test_json_summary_carries_registry_slug(self, runner: CliRunner, tmp_path: Path) -> None:
        # The Hub Composer navigates by this field; --no-register leaves it empty
        # rather than absent, so the consumer never has to guess.
        project = tmp_path / "slugproj"
        project.mkdir()
        result = runner.invoke(
            cli,
            [
                "init",
                "--agent",
                "claude",
                "-d",
                str(project),
                "--yes",
                "--no-index",
                "--no-register",
                "--format",
                "json",
            ],
        )
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output[result.output.index("{") :])
        assert payload["slug"] == ""

    def test_adopt_honours_module_profile(self, runner: CliRunner, tmp_path: Path) -> None:
        from cli.subsystems import resolve_profile

        project = tmp_path / "brownfield"
        project.mkdir()
        (project / "pyproject.toml").write_text("[project]\nname='x'\n")
        with runner.isolated_filesystem(temp_dir=tmp_path):
            os.environ["PWD"] = str(project)
            result = runner.invoke(
                cli,
                [
                    "adopt",
                    "--agent",
                    "claude",
                    "--profile",
                    "lite",
                    "--yes",
                    "--no-index",
                    "--no-register",
                ],
            )
        assert result.exit_code == 0, result.output
        state = json.loads((project / ".coding-os" / "subsystems-state.json").read_text())
        assert sorted(state["disabled"]) == sorted(resolve_profile("lite"))

    def test_unknown_skill_fails_fast(self, runner: CliRunner, tmp_path: Path) -> None:
        project = tmp_path / "badskill"
        project.mkdir()
        result = runner.invoke(
            cli,
            [
                "init",
                "--agent",
                "claude",
                "-d",
                str(project),
                "--skills",
                "no-such-skill",
                "--yes",
                "--no-index",
                "--no-register",
            ],
        )
        assert result.exit_code == 2
        assert "no-such-skill" in result.output
        assert not (project / ".coding-os.yaml").exists()  # failed BEFORE any write

    def test_non_tty_without_target_fails_fast(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("PWD", str(tmp_path))
        result = runner.invoke(cli, ["init", "--agent", "claude"])
        assert result.exit_code == 2
        assert "--name" in result.output and "--project-dir" in result.output
        assert list(tmp_path.iterdir()) == []  # nothing scaffolded

    def test_non_tty_without_agent_names_the_flag(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("PWD", str(tmp_path))
        result = runner.invoke(cli, ["init"])
        assert result.exit_code == 2
        assert "--agent" in result.output
