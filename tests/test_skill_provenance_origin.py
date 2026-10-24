"""A skill's provenance records where to fetch it again, not a scratch path.

Spec: docs/engineering/skill-architecture.md § import gate, step 4 (Provenance).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from cli.skill_commands import _origin


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
    ).stdout.strip()


def test_a_local_import_from_a_checkout_records_repo_commit_and_path(tmp_path: Path) -> None:
    repo = tmp_path / "skills-repo"
    skill = repo / "packs" / "trader"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\nname: trader\n---\n", encoding="utf-8")
    _git(repo, "init", "-q")
    _git(repo, "remote", "add", "origin", "https://example.com/skills.git")
    _git(repo, "add", ".")
    _git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "seed")

    origin = _origin("packs/trader", skill, from_url=False)

    assert origin["path"] == str(skill.resolve())
    assert origin["repo_url"] == "https://example.com/skills.git"
    assert origin["commit"] == _git(repo, "rev-parse", "HEAD")
    assert origin["path_in_repo"] == "packs/trader"


def test_a_plain_directory_records_only_its_absolute_path(tmp_path: Path) -> None:
    skill = tmp_path / "loose"
    skill.mkdir()

    assert _origin("loose", skill, from_url=False) == {"path": str(skill.resolve())}
