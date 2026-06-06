"""Tests for D.2 — interactive `cos init` with --yes + idempotent detection.

Uses click.testing.CliRunner so we can drive prompts with piped input and
assert on output/exit code without shelling out.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from cli.main import (
    _detect_existing_install,
    _sync_missing,
    cli as cos_cli,
)

pytestmark = pytest.mark.slow  # whole file scaffolds sandboxes / spawns subprocesses


class TestYesFlagGating:
    def test_yes_requires_agent(self, tmp_path: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(
            cos_cli,
            ["init", "--yes", "-d", str(tmp_path), "-n", "p"],
        )
        assert result.exit_code == 2
        assert "--agent is required" in result.output

    def test_yes_with_agent_succeeds(self, tmp_path: Path) -> None:
        runner = CliRunner()
        project = tmp_path / "p"
        project.mkdir()
        result = runner.invoke(
            cos_cli,
            ["init", "--yes", "-a", "claude", "--no-git", "-d", str(project)],
        )
        assert result.exit_code == 0
        assert (project / ".coding-os.yaml").exists()


class TestInteractivePrompts:
    def test_prompts_agent_when_missing(self, tmp_path: Path) -> None:
        runner = CliRunner()
        project = tmp_path / "p"
        project.mkdir()
        # Inputs: agent → "claude", templates → "0" (none), confirm current dir → "y"
        result = runner.invoke(
            cos_cli,
            ["init", "--no-git", "-d", str(project)],
            input="claude\n0\ny\n",
        )
        assert result.exit_code == 0, result.output
        assert "Agent" in result.output
        assert (project / ".coding-os.yaml").exists()

    def test_prompts_templates_when_missing(self, tmp_path: Path) -> None:
        runner = CliRunner()
        project = tmp_path / "p"
        project.mkdir()
        # Inputs: templates → "django" (by name), confirm current dir → "y"
        result = runner.invoke(
            cos_cli,
            ["init", "-a", "claude", "--no-git", "-d", str(project)],
            input="django\ny\n",
        )
        assert result.exit_code == 0, result.output
        import yaml

        cfg = yaml.safe_load((project / ".coding-os.yaml").read_text())
        assert "django" in cfg["templates"]

    def test_templates_numeric_selection(self, tmp_path: Path) -> None:
        runner = CliRunner()
        project = tmp_path / "p"
        project.mkdir()
        # Pick by index — "1,4" depends on registry ordering, use names instead.
        # But test the comma-separated path explicitly:
        result = runner.invoke(
            cos_cli,
            ["init", "-a", "claude", "--no-git", "-d", str(project)],
            input="django,nextjs\ny\n",
        )
        assert result.exit_code == 0, result.output
        import yaml

        cfg = yaml.safe_load((project / ".coding-os.yaml").read_text())
        assert set(cfg["templates"]) == {"django", "nextjs"}

    def test_templates_zero_means_none(self, tmp_path: Path) -> None:
        runner = CliRunner()
        project = tmp_path / "p"
        project.mkdir()
        result = runner.invoke(
            cos_cli,
            ["init", "-a", "claude", "--no-git", "-d", str(project)],
            input="0\ny\n",
        )
        assert result.exit_code == 0, result.output
        import yaml

        cfg = yaml.safe_load((project / ".coding-os.yaml").read_text())
        assert cfg["templates"] == []


class TestIdempotentDetection:
    def test_detect_missing_config_returns_none(self, tmp_path: Path) -> None:
        assert _detect_existing_install(tmp_path) is None

    def test_detect_reads_config(self, tmp_path: Path) -> None:
        (tmp_path / ".coding-os.yaml").write_text(
            "version: '1.0'\nagents: [claude]\ntemplates: [django]\n"
        )
        info = _detect_existing_install(tmp_path)
        assert info is not None
        assert info["agents"] == ["claude"]
        assert info["templates"] == ["django"]

    def test_sync_missing_relinks_removed_skill(self, tmp_path: Path) -> None:
        runner = CliRunner()
        project = tmp_path / "p"
        project.mkdir()
        # First: fresh install with django
        r1 = runner.invoke(
            cos_cli,
            ["init", "--yes", "-a", "claude", "-t", "django", "--no-git", "-d", str(project)],
        )
        assert r1.exit_code == 0
        skill = project / ".claude" / "skills" / "python-django" / "SKILL.md"
        assert skill.exists()
        # Remove it to simulate drift
        skill.unlink()
        assert not skill.exists()
        # Re-sync
        _sync_missing(project)
        assert skill.exists(), "sync did not re-link python-django"


# Removed test_rerun_in_same_dir_offers_sync — CliRunner keeps the process
# cwd so it could never exercise the rerun-detection path it was named for;
# its only real assertion (detection object shape) duplicates
# TestIdempotentDetection::test_detect_reads_config.


def test_valid_agents_resolves() -> None:
    from cli.main import VALID_AGENTS

    assert "claude" in VALID_AGENTS
    assert "codex" in VALID_AGENTS
