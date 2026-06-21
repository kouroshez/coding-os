"""Cross-project Hub live-agents roster (TASK-437).

GET /api/hub/agents walks the registry and scopes each project to its OWN state
dir + DB. The regression guards the per-project keying contract: no project's
state (task/slug) may leak into another's group.
"""

from __future__ import annotations

from pathlib import Path

import cli.registry as registry_mod
from cli.registry import ProjectEntry, Registry
from core.web.routes import presence


def _mk_project(tmp_path: Path, slug: str, task: str) -> Path:
    proj = tmp_path / slug
    agent_dir = proj / ".coding-os" / "claude"
    agent_dir.mkdir(parents=True)
    (agent_dir / "session-id").write_text(f"ses-{slug}\n", encoding="utf-8")
    (agent_dir / ".task-current").write_text(f"ses-{slug} {task}\n", encoding="utf-8")
    return proj


def test_cross_project_agents_groups_per_project(tmp_path: Path, monkeypatch) -> None:
    pa = _mk_project(tmp_path, "alpha", "TASK-AAA")
    pb = _mk_project(tmp_path, "beta", "TASK-BBB")
    fake = Registry(
        projects=[
            ProjectEntry(slug="alpha", path=str(pa), created_at="2026-01-01T00:00:00Z"),
            ProjectEntry(slug="beta", path=str(pb), created_at="2026-01-01T00:00:00Z"),
        ]
    )
    monkeypatch.setattr(registry_mod, "load_registry", lambda: fake)

    groups = presence.cross_project_agents()
    by_slug = {g["slug"]: g for g in groups}
    assert set(by_slug) == {"alpha", "beta"}, by_slug
    # No cross-project leak: each project's agent carries only its OWN task+slug.
    a = by_slug["alpha"]["agents"][0]
    assert a["task"] == "TASK-AAA" and a["slug"] == "alpha"
    b = by_slug["beta"]["agents"][0]
    assert b["task"] == "TASK-BBB" and b["slug"] == "beta"


def test_cross_project_agents_skips_projects_without_state_dir(tmp_path: Path, monkeypatch) -> None:
    ghost = tmp_path / "ghost"  # registered but no .coding-os/ → skipped, never raises
    ghost.mkdir()
    fake = Registry(
        projects=[ProjectEntry(slug="ghost", path=str(ghost), created_at="2026-01-01T00:00:00Z")]
    )
    monkeypatch.setattr(registry_mod, "load_registry", lambda: fake)
    assert presence.cross_project_agents() == []
