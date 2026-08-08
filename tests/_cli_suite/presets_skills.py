"""Part of tests/test_cli.py — collected via the aggregator, not directly."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from _cli_suite.shared import (
    cli,
    main_module,
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


# ---------------------------------------------------------------------------
# CLI onboarding parity — TASK-359 (--skills/--summary + non-TTY fail-fast)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Skill catalog SSOT — TASK-352 (skill-architecture.md § Per-stack skill groups)
# ---------------------------------------------------------------------------


class TestSkillCatalog:
    def test_stack_groups_derive_from_stack_yaml(self) -> None:
        from cli.skills_list import collect_stack_skill_groups

        payload = collect_stack_skill_groups("fastapi")
        groups = payload["groups"]
        required = {e["name"] for e in groups["required"]}
        recommended = {e["name"] for e in groups["recommended"]}
        optional = {e["name"] for e in groups["optional"]}
        assert "python-fastapi" in required  # primary_skill
        assert (
            "clean-code" in recommended and "api-design" in recommended
        )  # enforcement secondaries
        assert required.isdisjoint(recommended) and required.isdisjoint(optional)
        assert recommended.isdisjoint(optional)

    def test_stack_skill_resolves_with_provenance_and_validation(self) -> None:
        from cli.skills_list import collect_stack_skill_groups

        payload = collect_stack_skill_groups("fastapi")
        primary = payload["groups"]["required"][0]
        assert primary == {
            "name": "python-fastapi",
            "tier": "stack",
            "domain": ["backend"],
            "description": primary["description"],
            "provenance": "stack:fastapi",
            "validated": True,
        }
        assert primary["description"]  # sourced from frontmatter, non-empty
        assert payload["warnings"] == []

    def test_unknown_stack_raises_keyerror(self) -> None:
        from cli.skills_list import collect_stack_skill_groups

        with pytest.raises(KeyError):
            collect_stack_skill_groups("no-such-stack")

    def test_cli_stack_flag_matches_ssot_payload(self, runner: CliRunner) -> None:
        """Acceptance: CLI output and endpoint payload share the same SSOT function."""
        from cli.skills_list import collect_stack_skill_groups

        result = runner.invoke(
            main_module.cli, ["skills-list", "--stack", "meta", "--format", "json"]
        )
        assert result.exit_code == 0, result.output
        assert json.loads(result.output) == collect_stack_skill_groups("meta")

    def test_global_catalog_has_provenance_and_zero_warnings(self) -> None:
        from cli.skills_list import collect_skill_catalog

        catalog = collect_skill_catalog()
        provenances = {e["provenance"] for e in catalog["skills"]}
        assert "core" in provenances
        assert any(p.startswith("stack:") for p in provenances)
        assert catalog["count"] == len(catalog["skills"]) > 30
        assert catalog["warnings"] == []  # every stack SKILL.md is schema-valid
        assert all(e["validated"] for e in catalog["skills"])


class TestDoctorAgentSdk:
    def test_codex_optional_sdk_uses_data_driven_probe(
        self, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import importlib.metadata

        def missing_package(name: str):
            raise importlib.metadata.PackageNotFoundError(name)

        class FakeResult:
            stdout = "codex-cli 0.144.1"
            stderr = ""

        monkeypatch.setenv("COS_AGENT", "codex")
        monkeypatch.delenv("CODEX_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.setattr(importlib.metadata, "version", missing_package)
        monkeypatch.setattr(shutil, "which", lambda _: "/usr/bin/codex")
        monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: FakeResult())

        result = runner.invoke(cli, ["doctor", "--agent-sdk"])

        assert result.exit_code == 0, result.output
        assert "OpenAI Codex CLI SDK compatibility report" in result.output
        assert "openai-codex not installed" in result.output
        assert "uv sync --extra codex-sdk" in result.output
        assert "CODEX_API_KEY, OPENAI_API_KEY" in result.output
        assert "CLI fallback remains available" in result.output

    def test_legacy_claude_sdk_flag_remains_an_alias(
        self, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import importlib.metadata

        monkeypatch.setenv("COS_AGENT", "codex")
        monkeypatch.setattr(importlib.metadata, "version", lambda _: "0.1.0b3")
        monkeypatch.setattr(shutil, "which", lambda _: None)

        result = runner.invoke(cli, ["doctor", "--claude-sdk"])

        assert result.exit_code == 0, result.output
        assert "OpenAI Codex CLI SDK compatibility report" in result.output
        assert "openai-codex = 0.1.0b3" in result.output


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


# ---------------------------------------------------------------------------
# Description→PRD seeding — TASK-364
# ---------------------------------------------------------------------------


class TestDescriptionSeeding:
    def test_summary_renders_placeholder_and_seeds_verbatim_vision(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """Plain prose: placeholder rendered + degrade path writes the vision doc."""
        project = tmp_path / "seeded"
        project.mkdir()
        summary = "An invoice automation product for small agencies in MENA."
        result = runner.invoke(
            cli,
            [
                "init",
                "--agent",
                "claude",
                "-d",
                str(project),
                "--summary",
                summary,
                "--yes",
                "--no-index",
                "--no-register",
            ],
        )
        assert result.exit_code == 0, result.output
        index_doc = (project / "docs" / "00-index.md").read_text(encoding="utf-8")
        assert summary in index_doc
        assert "{{PROJECT_DESCRIPTION}}" not in index_doc
        vision = project / "docs" / "prd" / "01-snapshot-vision.md"
        assert summary in vision.read_text(encoding="utf-8")

    def test_structured_summary_routes_sections_by_keyword(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        project = tmp_path / "routed"
        project.mkdir()
        summary = (
            "## Vision\nAutomate invoices end to end.\n\n"
            "## Goals\nReach 1000 paying agencies in year one.\n"
        )
        result = runner.invoke(
            cli,
            [
                "init",
                "--agent",
                "claude",
                "-d",
                str(project),
                "--summary",
                summary,
                "--yes",
                "--no-index",
                "--no-register",
            ],
        )
        assert result.exit_code == 0, result.output
        prd = project / "docs" / "prd"
        assert "Automate invoices" in (prd / "01-snapshot-vision.md").read_text(encoding="utf-8")
        assert "1000 paying agencies" in (prd / "02-goals-kpis.md").read_text(encoding="utf-8")

    def test_no_summary_renders_generic_default(self, runner: CliRunner, tmp_path: Path) -> None:
        project = tmp_path / "plain"
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
            ],
        )
        assert result.exit_code == 0, result.output
        index_doc = (project / "docs" / "00-index.md").read_text(encoding="utf-8")
        assert "A software project managed by coding-os" in index_doc
        # Without a summary the scaffold's authoring TEMPLATE lands (TODO
        # blocks) — the seeded variant only wins when a description exists.
        vision = (project / "docs" / "prd" / "01-snapshot-vision.md").read_text(encoding="utf-8")
        assert "_TODO: write the elevator pitch._" in vision
        assert "onboarding intake" not in vision

    def test_seed_prd_is_idempotent(self, tmp_path: Path) -> None:
        from cli.setup import seed_prd_from_text

        project = tmp_path / "p"
        project.mkdir()
        first = seed_prd_from_text(project, "Just a plain description.")
        second = seed_prd_from_text(project, "Different text — must NOT overwrite.")
        assert first == ["docs/prd/01-snapshot-vision.md"]
        assert second == []
        content = (project / "docs" / "prd" / "01-snapshot-vision.md").read_text(encoding="utf-8")
        assert "Just a plain description." in content


# ---------------------------------------------------------------------------
# Subsystems module registry — TASK-349
# ---------------------------------------------------------------------------
