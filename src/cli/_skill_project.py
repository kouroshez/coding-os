"""Per-project skill enablement — `.coding-os.yaml` store + adapter symlinks.

Spec SSOT: docs/engineering/skill-architecture.md § Public skill standard.
Carries the project-config reader/writer, the provenance resolver, the
core/stack/community relink primitives, and the module→skill cascade that
`cos module enable|disable` drives. The `cos skill *` commands themselves stay
in cli.skill_commands.
"""

from __future__ import annotations

import os
from pathlib import Path

import click

from cli._resources import core_dir, templates_dir


def user_skills_dir() -> Path:
    """Community skill install root. Override with $COS_USER_SKILLS_DIR."""
    override = os.environ.get("COS_USER_SKILLS_DIR")
    if override:
        return Path(override)
    return Path.home() / ".coding-os" / "skills"


# --- Per-project extra skills (TASK-370) ---------------------------------
# SSOT is `.coding-os.yaml::extra_skills` (written by init/wizard since
# TASK-356/359) — no second YAML file. enable/disable mutate that list and
# (for community skills) maintain symlinks in every installed adapter's
# skills dir; core/stack skills are already wholesale-linked by the adapter.


def _project_config_path(project_root: Path) -> Path:
    return project_root / ".coding-os.yaml"


def _find_project_root() -> Path:
    current = Path.cwd().resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".coding-os.yaml").is_file():
            return candidate
    raise click.ClickException("not inside a coding-os project (.coding-os.yaml not found)")


def _load_project_config(project_root: Path) -> dict:
    import yaml

    return yaml.safe_load(_project_config_path(project_root).read_text(encoding="utf-8")) or {}


def _save_project_config(project_root: Path, config: dict) -> None:
    import yaml

    _project_config_path(project_root).write_text(
        yaml.dump(config, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )


def _installed_adapter_skills_dirs(project_root: Path) -> list[Path]:
    from cli._resources import adapters_dir
    from cli.adapter_registry import load_adapter_registry

    dirs: list[Path] = []
    for adapter in load_adapter_registry(adapters_dir()).values():
        if not adapter.skills_dir:
            continue
        agent_dir = project_root / adapter.skills_dir
        if agent_dir.parent.is_dir():
            dirs.append(agent_dir)
    return dirs


def _known_skill_provenance(name: str) -> str | None:
    """'core' | 'stack' | 'community' | None — where this skill name resolves."""
    if (core_dir("skills") / name / "SKILL.md").is_file():
        return "core"
    for stack_dir in templates_dir().iterdir():
        if (stack_dir / "skills" / name / "SKILL.md").is_file():
            return "stack"
    if (user_skills_dir() / name / "SKILL.md").is_file():
        return "community"
    return None


def _skill_source_skill_md(name: str, provenance: str) -> Path | None:
    """Absolute path to the source SKILL.md for a core/stack/community skill."""
    if provenance == "core":
        return core_dir("skills") / name / "SKILL.md"
    if provenance == "community":
        return user_skills_dir() / name / "SKILL.md"
    if provenance == "stack":
        for stack_dir in templates_dir().iterdir():
            candidate = stack_dir / "skills" / name / "SKILL.md"
            if candidate.is_file():
                return candidate
    return None


def _relink_core_stack_skill(
    project_root: Path, name: str, source_skill_md: Path, *, link: bool
) -> int:
    """Re-link (or unlink) a core/stack skill's SKILL.md in every installed
    adapter skills dir. Returns links touched. Linked as
    `<skills_dir>/<name>/SKILL.md` (parity with install-adapter.sh step 6)."""
    touched = 0
    for skills_root in _installed_adapter_skills_dirs(project_root):
        skill_dir = skills_root / name
        link_path = skill_dir / "SKILL.md"
        if link:
            skill_dir.mkdir(parents=True, exist_ok=True)
            if link_path.is_symlink() and not link_path.exists():
                link_path.unlink()  # dangling link (target moved) — clear before relink
            if not link_path.exists():
                link_path.symlink_to(source_skill_md)
                touched += 1
        else:
            if link_path.is_symlink() or link_path.exists():
                link_path.unlink()
                touched += 1
            try:
                skill_dir.rmdir()
            except OSError:
                pass  # dir not empty / absent — leave it
    return touched


def _relink_community_skill(project_root: Path, name: str, *, link: bool) -> int:
    """Re-link (or unlink) a community skill as a whole-DIR symlink so its
    supporting scripts ride along. Returns links touched."""
    source = user_skills_dir() / name
    touched = 0
    for skills_root in _installed_adapter_skills_dirs(project_root):
        link_path = skills_root / name
        if link:
            skills_root.mkdir(parents=True, exist_ok=True)
            if link_path.is_symlink() and not link_path.exists():
                link_path.unlink()  # dangling link (target moved) — clear before relink
            if not link_path.exists():
                link_path.symlink_to(source)
                touched += 1
        elif link_path.is_symlink():
            link_path.unlink()
            touched += 1
    return touched


def _installed_stack_skills(config: dict) -> set[str]:
    """Required skill names provided by the project's installed stacks."""
    from cli.skills_list import collect_stack_skill_groups

    out: set[str] = set()
    for stack_id in config.get("templates") or []:
        try:
            groups = collect_stack_skill_groups(stack_id)
        except Exception:
            continue
        out |= {entry["name"] for entry in groups.get("required", [])}
    return out


def set_project_skill(project_root: Path, name: str, enabled: bool) -> dict:
    """Shared CLI/web mutator: toggle any skill (core/stack/community) for a
    project. Community skills ride `extra_skills`; core/stack skills ride
    `disabled_skills` (a sibling key — one .coding-os.yaml store, no second
    file). The adapter SKILL.md symlink is relinked/unlinked inline so the
    toggle takes effect without a re-install."""
    provenance = _known_skill_provenance(name)
    if provenance is None:
        raise click.ClickException(
            f"unknown skill '{name}' — not in core, stack, or imported community skills"
        )
    config = _load_project_config(project_root)
    extras = list(config.get("extra_skills") or [])
    disabled = list(config.get("disabled_skills") or [])
    stack_skills = _installed_stack_skills(config)
    source = _skill_source_skill_md(name, provenance)

    # Community skills are opt-IN via extras; core/stack ship by default and are
    # opt-OUT via the disabled list. The two lists are mutually exclusive per id.
    if provenance == "community":
        if enabled:
            if name in extras:
                return {
                    "name": name,
                    "provenance": provenance,
                    "changed": False,
                    "note": "already enabled",
                }
            extras.append(name)
        else:
            if name not in extras:
                raise click.ClickException(f"'{name}' is not an extra skill of this project")
            extras.remove(name)
    else:  # core | stack
        if enabled:
            if name not in disabled:
                return {
                    "name": name,
                    "provenance": provenance,
                    "changed": False,
                    "note": "already enabled (core/stack skills ship by default)",
                }
            disabled.remove(name)
        else:
            if name in disabled:
                return {
                    "name": name,
                    "provenance": provenance,
                    "changed": False,
                    "note": "already disabled",
                }
            # A stack skill not installed by any current stack cannot be disabled.
            if provenance == "stack" and name not in stack_skills:
                raise click.ClickException(
                    f"'{name}' is a stack skill but no installed stack provides it"
                )
            disabled.append(name)

    config["extra_skills"] = extras
    config["disabled_skills"] = sorted(disabled)
    _save_project_config(project_root, config)

    if provenance == "community":
        links_touched = _relink_community_skill(project_root, name, link=enabled)
    elif source is not None:
        links_touched = _relink_core_stack_skill(project_root, name, source, link=enabled)
    else:
        links_touched = 0

    return {"name": name, "provenance": provenance, "changed": True, "links": links_touched}


# --- Module→skill cascade (TASK-475) -------------------------------------
# A module owns the skills it declares in subsystems.yaml::modules[].skills.
# Invariant: an owned skill is LINKED iff (at least one owning module is enabled)
# AND (the user has not opted it out via .coding-os.yaml::disabled_skills). The
# cascade is TARGETED per toggle (mirrors remove_stack._unlink_stack_skills), not
# a global reconcile. It records NOTHING in disabled_skills — that list is the
# user's explicit override, and conflating "module off" with "user opted out"
# would make a module re-enable unable to tell them apart; the linked-state is
# derived instead, and `cos doctor` surfaces any residue (modules.skill_drift).


def _safe_project_config(project_root: Path) -> dict:
    try:
        return _load_project_config(project_root)
    except (OSError, click.ClickException):
        return {}


def _toggle_skill_link(project_root: Path, name: str, *, link: bool) -> int:
    """Link/unlink one skill by provenance; 0 when the skill cannot be resolved."""
    provenance = _known_skill_provenance(name)
    if provenance is None:
        return 0
    if provenance == "community":
        return _relink_community_skill(project_root, name, link=link)
    source = _skill_source_skill_md(name, provenance)
    if source is None:
        return 0
    return _relink_core_stack_skill(project_root, name, source, link=link)


def planned_skill_unlinks(
    project_root: Path, module_id: str, modules: dict | None = None
) -> list[str]:
    """Owned skills `cos module disable <id>` would unlink now — ref-counted
    against other ENABLED owners (never the module itself). Drives the confirm."""
    from cli.subsystems import load_subsystems, module_state

    modules = modules or load_subsystems()
    if module_id not in modules:
        return []
    state = module_state(project_root, modules)
    still_owned = {
        skill
        for mid, module in modules.items()
        if mid != module_id and state.get(mid, True)
        for skill in module.skills
    }
    return [s for s in sorted(modules[module_id].skills) if s not in still_owned]


def cascade_module_skills(
    project_root: Path,
    module_id: str,
    enabled: bool,
    *,
    keep_skills: bool = False,
    modules: dict | None = None,
) -> dict:
    """Relink/unlink a module's owned skills after a module toggle.

    enable → relink each owned skill unless the user opted it out; disable →
    unlink each owned skill unless another enabled module still owns it (ref-count)
    or --keep-skills is set. Idempotent; returns the names touched per bucket."""
    from cli.subsystems import load_subsystems

    modules = modules or load_subsystems()
    owned = sorted(modules[module_id].skills) if module_id in modules else []
    if not owned:
        return {"module": module_id, "linked": [], "unlinked": [], "kept": []}

    config = _safe_project_config(project_root)
    user_disabled = set(config.get("disabled_skills") or [])
    installed_stack_skills = _installed_stack_skills(config)
    linked: list[str] = []
    unlinked: list[str] = []
    kept: list[str] = []

    if enabled:
        for name in owned:
            if name in user_disabled:
                kept.append(name)  # user override outranks the module relink
            elif _known_skill_provenance(name) == "stack" and name not in installed_stack_skills:
                # A meta-stack-owned skill (e.g. graph-os-authoring) that THIS
                # project never installed — never force-link it (mirrors the
                # set_project_skill stack guard, TASK-478). Only core skills ship
                # on every consumer, so only they cascade unconditionally.
                kept.append(name)
            elif _toggle_skill_link(project_root, name, link=True):
                linked.append(name)
    elif keep_skills:
        kept = owned
    else:
        candidates = set(planned_skill_unlinks(project_root, module_id, modules))
        for name in owned:
            if name not in candidates:
                kept.append(name)  # another enabled module still owns it
            elif _toggle_skill_link(project_root, name, link=False):
                unlinked.append(name)
    return {"module": module_id, "linked": linked, "unlinked": unlinked, "kept": kept}
