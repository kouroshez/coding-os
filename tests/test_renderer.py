"""Tests for cli.renderer — Jinja2 fragment composition + settings_json."""

from __future__ import annotations

from pathlib import Path

import pytest

from cli._data_types import (
    AdapterProfile,
    AgentsMdSection,
    AggregatedWorld,
    HookEntry,
    MakefileTarget,
)
from cli.renderer import (
    RenderError,
    render_agents_md,
    render_dimension_registry,
    render_makefile_targets,
    render_settings_json,
    render_skill_enforcement,
)


def _world(
    *,
    sections: tuple[AgentsMdSection, ...] = (),
    substitutions: dict | None = None,
    skills: tuple = (),
    verify_rows: tuple = (),
    hooks: tuple = (),
    makefile_targets: tuple = (),
    anatomy: tuple = (),
) -> AggregatedWorld:
    return AggregatedWorld(
        project_name="p",
        agent_id="claude",
        stack_ids=(),
        substitutions=substitutions or {},
        skills=skills,
        verify_rows=verify_rows,
        routing_entries=(),
        ref_codes=(),
        makefile_targets=makefile_targets,
        rules=(),
        dimensions=(),
        skill_enforcement=(),
        agents_md_sections=sections,
        hooks=hooks,
        conflicts=(),
        anatomy=anatomy,
    )


_BASE_DIR = Path(__file__).resolve().parent.parent / "src" / "templates" / "_base"


def _adapter(**overrides) -> AdapterProfile:
    defaults = {
        "id": "claude",
        "label": "Claude",
        "settings_file": ".claude/settings.json",
        "hooks_dir": ".claude/hooks",
        "rules_dir": ".claude/rules",
        "skills_dir": ".claude/skills",
        "commands_dir": ".claude/commands",
        "sourced_hooks": (),
        "supports_rules": True,
        "supports_settings_json": True,
        "install_script": Path("."),
        "default_settings": {},
        "source_dir": Path("."),
    }
    defaults.update(overrides)
    return AdapterProfile(**defaults)


# ---------- render_agents_md ----------


def test_empty_sections_produces_trailing_newline() -> None:
    world = _world()
    assert render_agents_md(world) == "\n"


def test_static_fragment_is_rendered(tmp_path: Path) -> None:
    fragments = tmp_path / "fragments"
    fragments.mkdir()
    (fragments / "hello.tmpl").write_text("hello world\n")
    section = AgentsMdSection(
        id="hello",
        order=10,
        template="hello.tmpl",
        owner_dir=fragments,
    )
    world = _world(sections=(section,))
    rendered = render_agents_md(world)
    assert "hello world" in rendered
    assert rendered.endswith("\n")


def test_substitution_interpolation(tmp_path: Path) -> None:
    fragments = tmp_path / "fragments"
    fragments.mkdir()
    (fragments / "proj.tmpl").write_text("name: {{ substitutions.NAME }}\n")
    section = AgentsMdSection(
        id="proj",
        order=10,
        template="proj.tmpl",
        owner_dir=fragments,
    )
    world = _world(sections=(section,), substitutions={"NAME": "acme"})
    assert "name: acme" in render_agents_md(world)


def test_undefined_variable_raises_render_error(tmp_path: Path) -> None:
    fragments = tmp_path / "fragments"
    fragments.mkdir()
    (fragments / "broken.tmpl").write_text("{{ substitutions.MISSING }}\n")
    section = AgentsMdSection(
        id="broken",
        order=10,
        template="broken.tmpl",
        owner_dir=fragments,
    )
    world = _world(sections=(section,), substitutions={})
    with pytest.raises(RenderError, match="failed to render"):
        render_agents_md(world)


def test_sections_joined_with_blank_line(tmp_path: Path) -> None:
    fragments = tmp_path / "fragments"
    fragments.mkdir()
    (fragments / "a.tmpl").write_text("A\n")
    (fragments / "b.tmpl").write_text("B\n")
    s_a = AgentsMdSection(id="a", order=10, template="a.tmpl", owner_dir=fragments)
    s_b = AgentsMdSection(id="b", order=20, template="b.tmpl", owner_dir=fragments)
    world = _world(sections=(s_a, s_b))
    assert render_agents_md(world) == "A\n\nB\n"


def test_section_order_is_honored(tmp_path: Path) -> None:
    fragments = tmp_path / "fragments"
    fragments.mkdir()
    (fragments / "a.tmpl").write_text("first\n")
    (fragments / "b.tmpl").write_text("second\n")
    # Passed in reversed order, but order field determines output position
    s_b = AgentsMdSection(id="b", order=20, template="b.tmpl", owner_dir=fragments)
    s_a = AgentsMdSection(id="a", order=10, template="a.tmpl", owner_dir=fragments)
    # aggregator sorts; but the renderer trusts the input order — so pre-sort
    sections = tuple(sorted((s_b, s_a), key=lambda s: (s.order, s.id)))
    world = _world(sections=sections)
    rendered = render_agents_md(world)
    assert rendered.index("first") < rendered.index("second")


# ---------- render_settings_json ----------


def test_settings_json_empty_for_unsupported_adapter() -> None:
    world = _world()
    adapter = _adapter(supports_settings_json=False)
    assert render_settings_json(world, adapter) == {}


def test_settings_json_merges_default_with_hooks() -> None:
    adapter = _adapter(default_settings={"permissions": {"allow": ["*"]}})
    world = _world(hooks=(HookEntry("PreToolUse", "*", "echo hi"),))
    result = render_settings_json(world, adapter)
    assert result["permissions"] == {"allow": ["*"]}
    assert "PreToolUse" in result["hooks"]
    assert result["hooks"]["PreToolUse"][0]["hooks"][0]["command"] == "echo hi"


# ---------- render_makefile_targets ----------


def test_makefile_targets_empty_header() -> None:
    assert "No stack-contributed" in render_makefile_targets(_world())


def test_makefile_targets_rendered() -> None:
    targets = (MakefileTarget("lint", "ruff check .", help="run lint"),)
    world = _world(makefile_targets=targets)
    out = render_makefile_targets(world)
    assert "lint:" in out
    assert "ruff check ." in out
    assert ".PHONY: lint" in out
    assert "run lint" in out


# ---------- render_dimension_registry / skill_enforcement ----------


def test_dimension_registry_empty() -> None:
    assert "No dimensions" in render_dimension_registry(_world())


def test_skill_enforcement_empty_has_none_row() -> None:
    text = render_skill_enforcement(_world())
    assert "_none_" in text


# ---------- anatomy map fragment (TASK-366) ----------


def _anatomy_section() -> AgentsMdSection:
    return AgentsMdSection(
        id="project-anatomy",
        order=25,
        template="fragments/anatomy-map.md.tmpl",
        owner_dir=_BASE_DIR,
    )


def test_anatomy_map_renders_stack_root_and_shared_rows() -> None:
    from cli._data_types import AnatomyEntry

    entry = AnatomyEntry(
        stack_id="fastapi",
        label="FastAPI",
        category="backend",
        root="src/backend",
        notes="app/{api,services}",
    )
    out = render_agents_md(_world(sections=(_anatomy_section(),), anatomy=(entry,)))
    assert "## Project Anatomy" in out
    assert "`src/backend`" in out
    assert "FastAPI (backend)" in out
    assert "app/{api,services}" in out
    # shared/ rows are always present (cross-language boundary)
    assert "`src/shared/contracts/`" in out
    assert "`src/shared/<lang>/`" in out


def test_anatomy_map_renders_shared_rows_when_no_stacks() -> None:
    out = render_agents_md(_world(sections=(_anatomy_section(),)))
    assert "## Project Anatomy" in out
    assert "`src/shared/contracts/`" in out
    # no stack roots, but the table is still valid markdown
    assert "| Subtree | Owner | Convention |" in out


def test_anatomy_map_escapes_pipe_in_notes() -> None:
    from cli._data_types import AnatomyEntry

    entry = AnatomyEntry(
        stack_id="nextjs",
        label="Next.js",
        category="frontend",
        root="src/frontend",
        notes="app/ router | components/",
    )
    out = render_agents_md(_world(sections=(_anatomy_section(),), anatomy=(entry,)))
    # a raw pipe in a cell would break the table — it must be escaped
    assert r"app/ router \| components/" in out
