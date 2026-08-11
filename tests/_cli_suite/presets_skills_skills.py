"""Part of tests/test_cli.py — collected via the aggregator, not directly."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from _cli_suite.shared import (
    cli,
    main_module,
)


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
