"""Tests for cli.aggregator — merge rules, derivation, conflict detection."""

from __future__ import annotations

from pathlib import Path

import pytest

from cli._data_types import (
    AdapterProfile,
    BaseProfile,
    HookEntry,
    MakefileTarget,
    RefCode,
    StackProfile,
    VerifyRow,
)
from cli.aggregator import AggregationError, aggregate as _raw_aggregate

FIXED_DATE = "2026-01-01"


def aggregate(base, stacks, adapter, project_name):
    """Test helper — always uses a fixed date for determinism."""
    return _raw_aggregate(
        base,
        stacks,
        adapter,
        project_name,
        today=FIXED_DATE,
    )


def _dummy_base(**overrides) -> BaseProfile:
    defaults = {
        "id": "base",
        "label": "Base",
        "skills": ("clean-code",),
        "substitutions": {"PROJECT_NAME": "${auto:project_name}"},
        "verify": (VerifyRow("docs/", "docs-lint", "`make docs-lint`"),),
        "routing_entries": (),
        "ref_codes": (),
        "makefile_targets": (),
        "rules": (),
        "dimensions": (),
        "skill_enforcement": (),
        "agents_md_sections": (),
        "hooks": (),
        "source_dir": Path("."),
    }
    defaults.update(overrides)
    return BaseProfile(**defaults)


def _dummy_stack(stack_id: str, **overrides) -> StackProfile:
    defaults = {
        "id": stack_id,
        "label": f"{stack_id} label",
        "category": "backend",
        "primary_skill": None,
        "skills": (),
        "substitutions": {},
        "verify": (),
        "routing_entries": (),
        "ref_codes": (),
        "makefile_targets": (),
        "rules": (),
        "dimensions": (),
        "skill_enforcement": (),
        "agents_md_sections": (),
        "hooks": (),
        "source_dir": Path("."),
    }
    defaults.update(overrides)
    return StackProfile(**defaults)


def _dummy_adapter() -> AdapterProfile:
    return AdapterProfile(
        id="claude",
        label="Claude",
        settings_file=".claude/settings.json",
        hooks_dir=".claude/hooks",
        rules_dir=".claude/rules",
        skills_dir=".claude/skills",
        commands_dir=".claude/commands",
        sourced_hooks=(),
        supports_rules=True,
        supports_settings_json=True,
        install_script=Path("."),
        default_settings={},
        source_dir=Path("."),
    )


# ---------- substitution merge + auto tokens ----------


def test_auto_project_name_resolved() -> None:
    world = aggregate(_dummy_base(), [], _dummy_adapter(), "my-proj")
    assert world.substitutions["PROJECT_NAME"] == "my-proj"


def test_stack_overrides_base_substitution() -> None:
    base = _dummy_base(substitutions={"K": "base_v"})
    stack = _dummy_stack("s", substitutions={"K": "stack_v"})
    world = aggregate(base, [stack], _dummy_adapter(), "p")
    assert world.substitutions["K"] == "stack_v"
    assert any("conflict on 'K'" in c for c in world.conflicts)


def test_stack_label_override_for_STACK_key() -> None:
    base = _dummy_base(substitutions={"STACK": "Polyglot"})
    s1 = _dummy_stack("s1", label="Django")
    s2 = _dummy_stack("s2", label="Next.js")
    world = aggregate(base, [s1, s2], _dummy_adapter(), "p")
    assert world.substitutions["STACK"] == "Django | Next.js"


def test_installed_skills_derived_as_backtick_list() -> None:
    base = _dummy_base(skills=("clean-code",))
    stack = _dummy_stack("s", skills=("python-django",))
    world = aggregate(base, [stack], _dummy_adapter(), "p")
    assert world.substitutions["INSTALLED_SKILLS"] == "`clean-code`, `python-django`"


# ---------- verify row dedupe ----------


def test_verify_rows_dedupe_by_glob_and_suites() -> None:
    row_a = VerifyRow("x/", "a", "`a`")
    row_b = VerifyRow("x/", "a", "`b`")  # same key, different cmd
    base = _dummy_base(verify=(row_a,))
    stack = _dummy_stack("s", verify=(row_b,))
    world = aggregate(base, [stack], _dummy_adapter(), "p")
    assert len(world.verify_rows) == 1
    assert world.verify_rows[0].cmd == "`a`"  # first-wins


# ---------- ref code dedupe + conflict ----------


def test_ref_codes_conflict_is_warned() -> None:
    base = _dummy_base(ref_codes=(RefCode("REF:X", "./a.md", ""),))
    stack = _dummy_stack("s", ref_codes=(RefCode("REF:X", "./b.md", ""),))
    world = aggregate(base, [stack], _dummy_adapter(), "p")
    assert len(world.ref_codes) == 1
    assert any("REF:X" in c for c in world.conflicts)


# ---------- makefile target dedupe ----------


def test_makefile_target_conflict_is_warned() -> None:
    t1 = MakefileTarget("lint", "cmd1")
    t2 = MakefileTarget("lint", "cmd2")
    base = _dummy_base(makefile_targets=(t1,))
    stack = _dummy_stack("s", makefile_targets=(t2,))
    world = aggregate(base, [stack], _dummy_adapter(), "p")
    assert len(world.makefile_targets) == 1
    assert any("lint" in c for c in world.conflicts)


# ---------- hook conflict = error ----------


def test_duplicate_hook_raises_aggregation_error() -> None:
    h1 = HookEntry("PreToolUse", "*", "cmd")
    h2 = HookEntry("PreToolUse", "*", "cmd")
    base = _dummy_base(hooks=(h1,))
    stack = _dummy_stack("s", hooks=(h2,))
    with pytest.raises(AggregationError, match="duplicate hook"):
        aggregate(base, [stack], _dummy_adapter(), "p")


# ---------- skills merge preserves order, dedupes ----------


def test_skills_preserve_first_occurrence_order() -> None:
    base = _dummy_base(skills=("a", "b"))
    s1 = _dummy_stack("s1", skills=("b", "c"))
    s2 = _dummy_stack("s2", skills=("d", "a"))
    world = aggregate(base, [s1, s2], _dummy_adapter(), "p")
    assert world.skills == ("a", "b", "c", "d")


# ---------- derived routing joins ----------


def test_routing_joined_on_pipe() -> None:
    base = _dummy_base(substitutions={"DOMAIN_ROUTES": "base route"})
    s1 = _dummy_stack("s1", substitutions={"DOMAIN_ROUTES": "s1 route"})
    s2 = _dummy_stack("s2", substitutions={"DOMAIN_ROUTES": "s2 route"})
    world = aggregate(base, [s1, s2], _dummy_adapter(), "p")
    assert world.substitutions["DOMAIN_ROUTES"] == "s1 route | s2 route"


def test_quick_routing_joined_on_newline() -> None:
    base = _dummy_base(substitutions={"QUICK_ROUTING": "- base"})
    s1 = _dummy_stack("s1", substitutions={"QUICK_ROUTING": "- one"})
    s2 = _dummy_stack("s2", substitutions={"QUICK_ROUTING": "- two"})
    world = aggregate(base, [s1, s2], _dummy_adapter(), "p")
    assert world.substitutions["QUICK_ROUTING"] == "- one\n- two"


# ---------- no stacks → base defaults retained ----------


def test_base_only_keeps_defaults() -> None:
    base = _dummy_base(substitutions={"STACK": "Polyglot", "DOMAIN_ROUTES": "anywhere"})
    world = aggregate(base, [], _dummy_adapter(), "p")
    assert world.substitutions["STACK"] == "Polyglot"
    assert world.substitutions["DOMAIN_ROUTES"] == "anywhere"


# ---------- anatomy map (TASK-366) ----------


def test_anatomy_built_from_stack_structure() -> None:
    stack = _dummy_stack(
        "fastapi",
        label="FastAPI",
        category="backend",
        structure={"root": "src/backend", "notes": "app/{api,services,db}"},
    )
    world = aggregate(_dummy_base(), [stack], _dummy_adapter(), "p")
    assert len(world.anatomy) == 1
    entry = world.anatomy[0]
    assert (entry.stack_id, entry.root, entry.category) == ("fastapi", "src/backend", "backend")
    assert entry.label == "FastAPI"
    assert entry.notes == "app/{api,services,db}"


def test_anatomy_reflects_relocated_root() -> None:
    # The world builder relocates colliding backends to src/services/<id>/
    # BEFORE aggregate() sees them, so anatomy carries the relocated root.
    relocated = _dummy_stack(
        "go-fiber", category="backend", structure={"root": "src/services/go-fiber"}
    )
    world = aggregate(_dummy_base(), [relocated], _dummy_adapter(), "p")
    assert world.anatomy[0].root == "src/services/go-fiber"


def test_anatomy_empty_for_base_only() -> None:
    world = aggregate(_dummy_base(), [], _dummy_adapter(), "p")
    assert world.anatomy == ()


def test_anatomy_skips_stack_without_root() -> None:
    stack = _dummy_stack("nostruct")  # no structure declared
    world = aggregate(_dummy_base(), [stack], _dummy_adapter(), "p")
    assert world.anatomy == ()


def test_anatomy_renders_into_agents_md_end_to_end() -> None:
    # full pipeline: aggregate() builds world.anatomy from the stack, then the
    # real fragment renders it into AGENTS.md (criterion 1 end-to-end).
    from cli._data_types import AgentsMdSection
    from cli.renderer import render_agents_md

    base_dir = Path(__file__).resolve().parent.parent / "src" / "templates" / "_base"
    section = AgentsMdSection(
        id="project-anatomy",
        order=25,
        template="fragments/anatomy-map.md.tmpl",
        owner_dir=base_dir,
    )
    stack = _dummy_stack(
        "fastapi",
        label="FastAPI",
        category="backend",
        structure={"root": "src/backend", "notes": "app/{api,services}"},
    )
    world = aggregate(_dummy_base(agents_md_sections=(section,)), [stack], _dummy_adapter(), "p")
    out = render_agents_md(world)
    assert "## Project Anatomy" in out
    assert "`src/backend`" in out
    assert "FastAPI (backend)" in out
    assert "app/{api,services}" in out
    assert "`src/shared/contracts/`" in out
