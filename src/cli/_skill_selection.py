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


def _stack_shipped_skill_names(stack_ids: list[str]) -> set[str]:
    from cli.stack_registry import load_stack_registry

    stacks = load_stack_registry(templates_dir(), overlay_dirs=overlay_template_dirs())
    names: set[str] = set()
    for stack_id in stack_ids:
        if stack_id not in stacks:
            continue
        skills_root = stacks[stack_id].source_dir / "skills"
        if skills_root.is_dir():
            names |= {p.name for p in skills_root.iterdir() if (p / "SKILL.md").is_file()}
    return names


def selected_skill_names(project_root: Path) -> frozenset[str]:
    """Base + each stack's required and recommended skills + extras, minus opt-outs."""
    from cli._pr_shared import _git_settings
    from cli.stack_registry import load_base_profile, load_stack_registry

    config = _safe_project_config(project_root)
    names = _declared_skill_names(load_base_profile(templates_dir("_base")))
    stacks = load_stack_registry(templates_dir(), overlay_dirs=overlay_template_dirs())
    for stack_id in config.get("templates") or []:
        if stack_id in stacks:
            names |= _declared_skill_names(stacks[stack_id])
    names |= {str(name) for name in config.get("extra_skills") or []}
    if _git_settings(str(project_root)).get("enabled"):
        names.add(PR_MODE_SKILL)
    names -= _skills_owned_only_by_disabled_modules(project_root)
    names -= {str(name) for name in config.get("disabled_skills") or []}
    return frozenset(names)


def _user_owns_copy(project_root: Path, name: str) -> bool:
    for skills_root in _installed_adapter_skills_dirs(project_root):
        skill_md = skills_root / name / "SKILL.md"
        if skill_md.exists() and not skill_md.is_symlink():
            return True
    return False


def reconcile_core_skills_in_link_form(project_root: Path) -> tuple[list[str], list[str]]:
    """Reconcile a clone-ready project, whose skills are copies until delocalized."""
    from cli._localize_links import link_form

    with link_form(project_root):
        return reconcile_core_skills(project_root)


def reconcile_core_skills(project_root: Path) -> tuple[list[str], list[str]]:
    """Link the selected core skills and unlink the rest; returns (linked, unlinked)."""
    selected = selected_skill_names(project_root)
    stack_shipped = _stack_shipped_skill_names(
        list(_safe_project_config(project_root).get("templates") or [])
    )
    linked: list[str] = []
    unlinked: list[str] = []
    for skill_dir in sorted(core_dir("skills").iterdir()):
        skill_md = skill_dir / "SKILL.md"
        name = skill_dir.name
        if not skill_md.is_file() or name in stack_shipped:
            continue
        wanted = name in selected
        if not wanted and _user_owns_copy(project_root, name):
            continue
        if _relink_core_stack_skill(project_root, name, skill_md, link=wanted):
            (linked if wanted else unlinked).append(name)
    return linked, unlinked
