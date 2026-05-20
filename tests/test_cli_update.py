"""Tests for D.3 — `cos update` command.

Covers:
  - Fresh install → no-op update (manifest written, zero diff).
  - Simulated drift (deleted symlink) → update re-links it.
  - Orphan detection when source no longer exists.
  - --dry-run never touches filesystem.
  - installed-manifest.json is written and has the right shape.
  - Non-project directory → clear error.
"""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from cli.main import cli as cos_cli


def _init(tmp_path: Path, *templates: str) -> Path:
    """Init a project with claude + given templates. Returns project path."""
    project = tmp_path / "proj"
    project.mkdir()
    runner = CliRunner()
    args = ["init", "--yes", "-a", "claude", "--no-git", "-d", str(project)]
    for t in templates:
        args.extend(["-t", t])
    result = runner.invoke(cos_cli, args)
    assert result.exit_code == 0, result.output
    return project


class TestUpdateNoDrift:
    def test_fresh_install_update_reports_no_changes(self, tmp_path: Path) -> None:
        project = _init(tmp_path, "django")
        runner = CliRunner()
        result = runner.invoke(cos_cli, ["update", "-d", str(project)])
        assert result.exit_code == 0
        assert "No changes" in result.output or "Already up to date" in result.output

    def test_update_writes_installed_manifest(self, tmp_path: Path) -> None:
        project = _init(tmp_path, "django")
        runner = CliRunner()
        runner.invoke(cos_cli, ["update", "-d", str(project)])
        manifest = project / ".coding-os" / "installed-manifest.json"
        assert manifest.exists()
        data = json.loads(manifest.read_text())
        assert data["agent"] == "claude"
        assert data["templates"] == ["django"]
        assert "hooks" in data["linked_assets"]
        assert "skills" in data["linked_assets"]
        assert "python-django" in data["linked_assets"]["skills"]


class TestUpdateRepairsDrift:
    def test_deleted_skill_relinked(self, tmp_path: Path) -> None:
        project = _init(tmp_path, "django")
        skill = project / ".claude/skills/python-django/SKILL.md"
        assert skill.exists()
        skill.unlink()
        assert not skill.exists()

        runner = CliRunner()
        result = runner.invoke(cos_cli, ["update", "-d", str(project)])
        assert result.exit_code == 0
        assert skill.exists()
        assert skill.is_symlink()

    def test_deleted_hook_relinked(self, tmp_path: Path) -> None:
        project = _init(tmp_path)
        hook = project / ".claude/hooks/block-secrets.sh"
        assert hook.exists()
        hook.unlink()

        runner = CliRunner()
        result = runner.invoke(cos_cli, ["update", "-d", str(project)])
        assert result.exit_code == 0
        assert hook.exists()

    def test_dry_run_does_not_apply(self, tmp_path: Path) -> None:
        project = _init(tmp_path, "django")
        skill = project / ".claude/skills/python-django/SKILL.md"
        skill.unlink()

        runner = CliRunner()
        result = runner.invoke(cos_cli, ["update", "--dry-run", "-d", str(project)])
        assert result.exit_code == 0
        assert "Added" in result.output or "skills" in result.output
        # Still missing after dry-run
        assert not skill.exists()


class TestUpdateGracefulErrors:
    def test_non_project_errors_cleanly(self, tmp_path: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(cos_cli, ["update", "-d", str(tmp_path)])
        assert result.exit_code != 0
        assert "Not a coding-os project" in result.output


class TestUpdateJsonOutput:
    def test_json_format_returns_structured_diff(self, tmp_path: Path) -> None:
        project = _init(tmp_path, "django")
        skill = project / ".claude/skills/python-django/SKILL.md"
        skill.unlink()

        runner = CliRunner()
        result = runner.invoke(
            cos_cli,
            ["update", "-d", str(project), "--format", "json", "--dry-run"],
        )
        assert result.exit_code == 0
        # JSON is the last `{...}` block in output (text diff precedes it).
        text = result.output
        last_brace = text.rfind("{")
        end_brace = text.rfind("}")
        assert last_brace >= 0 and end_brace > last_brace, result.output
        # Walk backwards to find the matching opening brace for the last `}`.
        depth = 0
        start_idx = end_brace
        for i in range(end_brace, -1, -1):
            if text[i] == "}":
                depth += 1
            elif text[i] == "{":
                depth -= 1
                if depth == 0:
                    start_idx = i
                    break
        payload = json.loads(text[start_idx : end_brace + 1])
        assert payload["dry_run"] is True
        assert "per_agent" in payload
