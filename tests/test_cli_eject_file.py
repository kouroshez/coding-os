"""Tests for D.5 — `cos eject-file` command."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from cli.main import cli as cos_cli

pytestmark = pytest.mark.slow  # whole file scaffolds sandboxes / spawns subprocesses (TASK-008 L3)


def _init(tmp_path: Path) -> Path:
    project = tmp_path / "proj"
    project.mkdir()
    runner = CliRunner()
    result = runner.invoke(
        cos_cli,
        ["init", "--yes", "-a", "claude", "--no-git", "-d", str(project)],
    )
    assert result.exit_code == 0, result.output
    return project


class TestEjectFile:
    def test_ejects_symlink_to_copy(self, tmp_path: Path) -> None:
        project = _init(tmp_path)
        rel = ".claude/skills/thinking_os/SKILL.md"
        link = project / rel
        assert link.is_symlink()
        original_content = link.read_text()

        runner = CliRunner()
        result = runner.invoke(cos_cli, ["eject-file", rel, "-d", str(project)])
        assert result.exit_code == 0, result.output
        assert not link.is_symlink()
        assert link.is_file()
        assert link.read_text() == original_content

    def test_edit_after_eject_does_not_affect_source(self, tmp_path: Path) -> None:
        project = _init(tmp_path)
        rel = ".claude/skills/thinking_os/SKILL.md"
        link = project / rel
        source_path = link.resolve()
        source_original = source_path.read_text()

        runner = CliRunner()
        runner.invoke(cos_cli, ["eject-file", rel, "-d", str(project)])

        # Edit the ejected copy.
        link.write_text("MODIFIED by user\n")
        # Source must be untouched.
        assert source_path.read_text() == source_original

    def test_already_regular_errors_without_force(self, tmp_path: Path) -> None:
        project = _init(tmp_path)
        rel = ".claude/skills/thinking_os/SKILL.md"
        runner = CliRunner()
        runner.invoke(cos_cli, ["eject-file", rel, "-d", str(project)])
        # Second call on now-regular file
        result = runner.invoke(cos_cli, ["eject-file", rel, "-d", str(project)])
        assert result.exit_code != 0
        assert "already a regular file" in result.output.lower()

    def test_missing_path_errors(self, tmp_path: Path) -> None:
        project = _init(tmp_path)
        runner = CliRunner()
        result = runner.invoke(
            cos_cli,
            ["eject-file", ".claude/skills/nonexistent/SKILL.md", "-d", str(project)],
        )
        assert result.exit_code != 0

    def test_force_succeeds_on_already_ejected_file(self, tmp_path: Path) -> None:
        project = _init(tmp_path)
        rel = ".claude/skills/thinking_os/SKILL.md"
        runner = CliRunner()
        runner.invoke(cos_cli, ["eject-file", rel, "-d", str(project)])
        link = project / rel
        link.write_text("tampered")
        # Without --force a second eject errors (see test_already_regular_errors
        # _without_force); --force re-ejects an already-regular file cleanly.
        result = runner.invoke(cos_cli, ["eject-file", rel, "--force", "-d", str(project)])
        assert result.exit_code == 0, result.output
        # The path stays a real regular file — not deleted, not a dangling symlink.
        assert link.is_file() and not link.is_symlink()
