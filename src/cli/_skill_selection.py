"""Which skills a project installs: its base and stack skills, never the whole catalog."""

from __future__ import annotations

from pathlib import Path

from cli._resources import core_dir, overlay_template_dirs, templates_dir
from cli._skill_project import (
    _installed_adapter_skills_dirs,
    _relink_core_stack_skill,
    _safe_project_config,
)

PR_MODE_SKILL = "pr-mode-driver"


def _declared_skill_names(profile) -> set[str]:
    names = set(profile.skills)
    primary = getattr(profile, "primary_skill", None)
    if primary:
        names.add(primary)
    # A row's primary is what enforce-skill blocks on, so it must be installed.
    for row in profile.skill_enforcement:
        names.add(row.primary)
        names.update(row.secondary)
    return names


def _skills_owned_only_by_disabled_modules(project_root: Path) -> set[str]:
    from cli.subsystems import load_subsystems, module_state

    modules = load_subsystems()
    state = module_state(project_root, modules)
    enabled_owned = {s for mid, m in modules.items() if state.get(mid, True) for s in m.skills}
    disabled_owned = {s for mid, m in modules.items() if not state.get(mid, True) for s in m.skills}
    return disabled_owned - enabled_owned


def _installed_stacks(project_root: Path) -> list:
    from cli.stack_registry import load_stack_registry

    stacks = load_stack_registry(templates_dir(), overlay_dirs=overlay_template_dirs())
    wanted = _safe_project_config(project_root).get("templates") or []
    return [stacks[stack_id] for stack_id in wanted if stack_id in stacks]


def _with_dependencies(names: set[str], stacks: list) -> set[str]:
    # A skill that says it loads another (`depends_on:`) brings it along.
    from cli.skill_registry import load_skill_registry

    profiles = {p.name: p for p in load_skill_registry(core_dir("skills")).values()}
    for stack in stacks:
        if (stack.source_dir / "skills").is_dir():
            stack_reg = load_skill_registry(stack.source_dir / "skills")
            profiles.update({p.name: p for p in stack_reg.values()})
    closed = set(names)
    pending = list(names)
    while pending:
        profile = profiles.get(pending.pop())
        for dependency in profile.depends_on if profile else ():
            if dependency not in closed:
                closed.add(dependency)
                pending.append(dependency)
    return closed


def selected_skill_names(project_root: Path) -> frozenset[str]:
    from cli._pr_shared import _git_settings
    from cli.stack_registry import load_base_profile

    config = _safe_project_config(project_root)
    stacks = _installed_stacks(project_root)
    names = _declared_skill_names(load_base_profile(templates_dir("_base")))
    for stack in stacks:
        names |= _declared_skill_names(stack)
    names |= {str(name) for name in config.get("extra_skills") or []}
    if _git_settings(str(project_root)).get("enabled"):
        names.add(PR_MODE_SKILL)
    names = _with_dependencies(names, stacks)
    names -= _skills_owned_only_by_disabled_modules(project_root)
    names -= {str(name) for name in config.get("disabled_skills") or []}
    return frozenset(names)


def _user_owns_copy(skills_roots: list[Path], name: str) -> bool:
    for skills_root in skills_roots:
        skill_md = skills_root / name / "SKILL.md"
        if skill_md.exists() and not skill_md.is_symlink():
            return True
    return False


def _parked_skill_names(kept: list[str]) -> set[str]:
    # link_form parks an edited copy aside for the step; it is still the user's.
    return {
        parts[2]
        for parts in (rel.split("/") for rel in kept)
        if len(parts) > 3 and parts[1] == "skills"
    }


def reconcile_core_skills_in_link_form(project_root: Path) -> tuple[list[str], list[str]]:
    from cli._localize_links import link_form

    with link_form(project_root) as kept:
        return reconcile_core_skills(project_root, kept)


def reconcile_core_skills(
    project_root: Path, kept: list[str] | None = None
) -> tuple[list[str], list[str]]:
    selected = selected_skill_names(project_root)
    stack_shipped = {
        p.name
        for stack in _installed_stacks(project_root)
        if (stack.source_dir / "skills").is_dir()
        for p in (stack.source_dir / "skills").iterdir()
        if (p / "SKILL.md").is_file()
    }
    parked = _parked_skill_names(kept or [])
    skills_roots = _installed_adapter_skills_dirs(project_root)
    linked: list[str] = []
    unlinked: list[str] = []
    for skill_dir in sorted(core_dir("skills").iterdir()):
        skill_md = skill_dir / "SKILL.md"
        name = skill_dir.name
        if not skill_md.is_file() or name in stack_shipped:
            continue
        wanted = name in selected
        if not wanted and (name in parked or _user_owns_copy(skills_roots, name)):
            continue
        if _relink_core_stack_skill(
            project_root, name, skill_md, link=wanted, skills_roots=skills_roots
        ):
            (linked if wanted else unlinked).append(name)
    return linked, unlinked


def apply_project_selection(project_root: Path) -> None:
    # An adapter install links the whole catalog (skills, commands, hooks); this
    # trims it to what the project's stacks and enabled modules ask for.
    from cli._localize_links import link_form
    from cli._module_rules_cascade import _cascade_hooks_after_toggle
    from cli.module_commands import cascade_module_commands
    from cli.subsystems import load_subsystems, module_state

    modules = load_subsystems()
    state = module_state(project_root, modules)
    with link_form(project_root) as kept:
        reconcile_core_skills(project_root, kept)
        for module_id, enabled in state.items():
            if not enabled:
                cascade_module_commands(project_root, module_id, enabled=False, modules=modules)
    _cascade_hooks_after_toggle(project_root)
