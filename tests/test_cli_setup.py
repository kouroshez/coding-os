"""Tests for D.4 — `cos setup` command (docs bootstrap).

Covers:
  - skip mode → no files written
  - interactive mode → writes 4 PRD files
  - import-prd mode → parses H2 sections, routes by keyword classifier
  - idempotent — never overwrites existing files
  - classifier catches fallback `99-misc.md` for unknown headings
  - error paths: no config, missing source file
"""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from cli.main import cli as cos_cli
from cli.setup import (
    PRD_CLASSIFIER,
    _classify_section,
    _parse_markdown_sections,
)

pytestmark = pytest.mark.slow  # dominated by cos-init / subprocess tests


def _init(tmp_path: Path, *templates: str) -> Path:
    project = tmp_path / "proj"
    project.mkdir()
    runner = CliRunner()
    args = ["init", "--yes", "-a", "claude", "--no-git", "-d", str(project)]
    for t in templates:
        args.extend(["-t", t])
    result = runner.invoke(cos_cli, args)
    assert result.exit_code == 0, result.output
    return project


class TestClassifier:
    def test_vision_keyword_routes_to_01(self) -> None:
        assert _classify_section("Vision") == "01-snapshot-vision.md"
        assert _classify_section("Elevator Pitch") == "01-snapshot-vision.md"

    def test_goals_keyword_routes_to_02(self) -> None:
        assert _classify_section("Goals and KPIs") == "02-goals-kpis.md"
        assert _classify_section("Success Metrics") == "02-goals-kpis.md"

    def test_persona_keyword_routes_to_03(self) -> None:
        assert _classify_section("Primary Persona") == "03-users-jobs.md"
        assert _classify_section("Audience") == "03-users-jobs.md"

    def test_unknown_heading_falls_back_to_misc(self) -> None:
        assert _classify_section("Something Completely Random") == "99-misc.md"

    def test_case_insensitive(self) -> None:
        assert _classify_section("VISION") == "01-snapshot-vision.md"
        assert _classify_section("vision") == "01-snapshot-vision.md"


class TestMarkdownParser:
    def test_splits_on_h2(self) -> None:
        md = "# Title\n\nIntro\n\n## First\nbody1\n\n## Second\nbody2\n"
        sections = _parse_markdown_sections(md)
        assert len(sections) == 2
        assert sections[0][0] == "First"
        assert "body1" in sections[0][1]
        assert sections[1][0] == "Second"

    def test_content_before_first_h2_ignored(self) -> None:
        md = "# H1\nthis is intro, no H2\n"
        assert _parse_markdown_sections(md) == []

    def test_empty_h2_produces_empty_body(self) -> None:
        md = "## Empty\n## Next\nbody\n"
        sections = _parse_markdown_sections(md)
        assert len(sections) == 2
        assert sections[0] == ("Empty", "")


class TestSkipMode:
    def test_skip_writes_nothing(self, tmp_path: Path) -> None:
        project = _init(tmp_path)
        prd_dir = project / "docs" / "prd"
        before = sorted(p.name for p in prd_dir.iterdir())
        runner = CliRunner()
        result = runner.invoke(cos_cli, ["setup", "--mode", "skip", "-d", str(project)])
        assert result.exit_code == 0
        assert "Skipped" in result.output
        # skip mode adds nothing beyond what the scaffold already wrote
        assert sorted(p.name for p in prd_dir.iterdir()) == before


class TestInteractiveMode:
    def test_interactive_fills_prd_files(self, tmp_path: Path) -> None:
        project = _init(tmp_path)
        runner = CliRunner()
        result = runner.invoke(
            cos_cli,
            ["setup", "--mode", "interactive", "-d", str(project)],
            input="my vision\nkpi1,kpi2\nartisan\nsearch,checkout\n",
        )
        assert result.exit_code == 0, result.output
        prd = project / "docs" / "prd"
        for name in (
            "01-snapshot-vision.md",
            "02-goals-kpis.md",
            "03-users-jobs.md",
            "08-functional-requirements.md",
        ):
            assert (prd / name).exists()
        # 01-snapshot-vision.md ships in the scaffold as a guided template, so
        # setup idempotently skips it (transparent SKIP notice) and the frame
        # stays authoritative. The files setup creates carry the answers.
        assert "SKIP existing: docs/prd/01-snapshot-vision.md" in result.output
        assert "kpi1" in (prd / "02-goals-kpis.md").read_text()
        assert "artisan" in (prd / "03-users-jobs.md").read_text()

    def test_interactive_idempotent(self, tmp_path: Path) -> None:
        project = _init(tmp_path)
        # First run
        runner = CliRunner()
        runner.invoke(
            cos_cli,
            ["setup", "--mode", "interactive", "-d", str(project)],
            input="vision1\n\n\n\n",
        )
        vision_path = project / "docs" / "prd" / "01-snapshot-vision.md"
        original = vision_path.read_text()
        # Second run with different answers → should skip
        runner.invoke(
            cos_cli,
            ["setup", "--mode", "interactive", "-d", str(project)],
            input="vision2\n\n\n\n",
        )
        assert vision_path.read_text() == original


class TestImportPrdMode:
    def _write_sample_prd(self, path: Path) -> Path:
        path.write_text(
            "# Sample\n\n"
            "## Vision\nA marketplace.\n\n"
            "## Goals\n- 3K MAU\n\n"
            "## Persona\nArtisans.\n\n"
            "## Something Weird\nrandom stuff\n"
        )
        return path

    def test_import_writes_classified_files(self, tmp_path: Path) -> None:
        project = _init(tmp_path)
        source = self._write_sample_prd(tmp_path / "prd.md")
        runner = CliRunner()
        result = runner.invoke(
            cos_cli,
            ["setup", "--mode", "import-prd", "--source", str(source), "--yes", "-d", str(project)],
        )
        assert result.exit_code == 0, result.output
        prd = project / "docs" / "prd"
        assert (prd / "01-snapshot-vision.md").exists()
        assert (prd / "02-goals-kpis.md").exists()
        assert (prd / "03-users-jobs.md").exists()
        # Unknown heading → 99-misc.md
        assert (prd / "99-misc.md").exists()

    def test_import_preserves_original_headings(self, tmp_path: Path) -> None:
        project = _init(tmp_path)
        source = self._write_sample_prd(tmp_path / "prd.md")
        runner = CliRunner()
        runner.invoke(
            cos_cli,
            ["setup", "--mode", "import-prd", "--source", str(source), "--yes", "-d", str(project)],
        )
        # 01-snapshot-vision.md ships in the scaffold, so import idempotently
        # skips the "Vision" section; assert heading preservation on a file the
        # importer actually creates ("## Goals" → 02-goals-kpis.md).
        goals = (project / "docs/prd/02-goals-kpis.md").read_text()
        assert "## Goals" in goals
        assert "3K MAU" in goals

    def test_import_missing_source_errors(self, tmp_path: Path) -> None:
        project = _init(tmp_path)
        runner = CliRunner()
        result = runner.invoke(
            cos_cli,
            [
                "setup",
                "--mode",
                "import-prd",
                "--source",
                str(tmp_path / "nope.md"),
                "--yes",
                "-d",
                str(project),
            ],
        )
        assert result.exit_code != 0
        assert "not found" in result.output.lower()

    def test_import_no_h2_errors(self, tmp_path: Path) -> None:
        project = _init(tmp_path)
        source = tmp_path / "empty.md"
        source.write_text("# Just H1\nno h2 here\n")
        runner = CliRunner()
        result = runner.invoke(
            cos_cli,
            ["setup", "--mode", "import-prd", "--source", str(source), "--yes", "-d", str(project)],
        )
        assert result.exit_code != 0


class TestSetupErrors:
    def test_non_project_errors(self, tmp_path: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(
            cos_cli,
            ["setup", "--mode", "skip", "-d", str(tmp_path)],
        )
        assert result.exit_code != 0
        assert "Not a coding-os project" in result.output

    def test_yes_without_mode_errors(self, tmp_path: Path) -> None:
        project = _init(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cos_cli, ["setup", "--yes", "-d", str(project)])
        assert result.exit_code != 0


def test_classifier_coverage() -> None:
    """Every classifier target has at least one keyword."""
    for target, kws in PRD_CLASSIFIER.items():
        assert len(kws) >= 1, target
        assert target.endswith(".md")
