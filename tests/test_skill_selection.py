"""Which skills a project installs, and that reconciling never loses a user's edit."""

from __future__ import annotations

from pathlib import Path

import yaml

from cli._resources import core_dir
from cli._skill_project import _installed_adapter_skills_dirs
from cli._skill_selection import reconcile_core_skills, selected_skill_names


def _project(tmp_path: Path, **config) -> Path:
    project = tmp_path / "project"
    project.mkdir(parents=True)
    (project / ".coding-os.yaml").write_text(yaml.safe_dump(config), encoding="utf-8")
    return project


def test_agent_memory_does_not_make_a_claude_project_look_like_codex(tmp_path: Path) -> None:
    project = _project(tmp_path, agents=["claude"], templates=[])
    (project / ".agents" / "memory").mkdir(parents=True)
    (project / ".claude").mkdir()

    assert _installed_adapter_skills_dirs(project) == [project / ".claude" / "skills"]


def test_a_skill_a_stack_skill_depends_on_is_installed(tmp_path: Path) -> None:
    project = _project(tmp_path, agents=["claude"], templates=["node-express"])

    assert "node-backend" in selected_skill_names(project)


def test_an_optional_skill_is_left_out_until_named(tmp_path: Path) -> None:
    project = _project(tmp_path, agents=["claude"], templates=["fastapi"])
    assert "docker" not in selected_skill_names(project)

    named = _project(
        tmp_path / "named", agents=["claude"], templates=["fastapi"], extra_skills=["docker"]
    )
    assert "docker" in selected_skill_names(named)


def test_a_parked_edit_keeps_its_skill_through_reconcile(tmp_path: Path) -> None:
    project = _project(tmp_path, agents=["claude"], templates=[])
    skill = project / ".claude" / "skills" / "docker"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").symlink_to(core_dir("skills", "docker", "SKILL.md"))

    reconcile_core_skills(project, kept=[".claude/skills/docker/SKILL.md"])
    assert (skill / "SKILL.md").exists()

    reconcile_core_skills(project)
    assert not skill.exists()
