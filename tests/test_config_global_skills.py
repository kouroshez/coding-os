"""Global skills: */SKILL.md under each adapter's home skills_dir, merged by name."""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
for _p in (_REPO_ROOT, _REPO_ROOT / "src", _REPO_ROOT / "src" / "core"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from core.web.routes import _config_read


def _skill(root: Path, folder: str, frontmatter: str) -> None:
    (root / folder).mkdir(parents=True)
    (root / folder / "SKILL.md").write_text(f"---\n{frontmatter}\n---\n\nbody\n", encoding="utf-8")


def test_merges_one_skill_across_adapters_and_reads_its_frontmatter(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    _skill(tmp_path / ".claude" / "skills", "shared", "name: shared\ndescription: used by both")
    _skill(tmp_path / ".codex" / "skills", "shared", "name: shared\ndescription: used by both")
    _skill(tmp_path / ".claude" / "skills", "solo", "description: no name field")
    (tmp_path / ".claude" / "skills" / ".hidden").mkdir()
    (tmp_path / ".claude" / "skills" / "no-skill-md").mkdir()

    rows = {row["name"]: row for row in _config_read._global_skills()}

    assert set(rows) == {"shared", "solo"}
    assert rows["shared"] == {
        "name": "shared",
        "description": "used by both",
        "adapters": ["claude", "codex"],
    }
    assert rows["solo"]["adapters"] == ["claude"]


def test_no_home_skill_folders_means_no_global_skills(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    assert _config_read._global_skills() == []
