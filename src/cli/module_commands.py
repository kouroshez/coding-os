"""`cos module list|enable|disable` — subsystem toggles + dependent regen (TASK-354).

Wraps cli.subsystems (the state SSOT, TASK-349). A successful toggle
regenerates everything the module state feeds: AGENTS.md (conditional
sections, TASK-353) and the runtime hook allowlist (TASK-256/353).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import click

from cli.subsystems import ToggleResult, load_subsystems, module_state, set_module_enabled

logger = logging.getLogger("cli.module")


def _project_root() -> Path:
    root = Path.cwd().resolve()
    if not (root / ".coding-os").is_dir():
        raise click.ClickException(
            f"{root} is not a coding-os project (.coding-os/ missing) — run from the project root."
        )
    return root


def regen_after_toggle(project: Path) -> list[str]:
    """Re-derive every artifact that depends on module state. Returns notes."""
    notes: list[str] = []

    from cli.project_overrides import write_runtime_allowlist

    allowlist = write_runtime_allowlist(project)
    notes.append(f"runtime hook allowlist → {allowlist.relative_to(project)}")

    import yaml as _yaml

    config_path = project / ".coding-os.yaml"
    try:
        config = _yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except (OSError, _yaml.YAMLError) as exc:
        notes.append(f"AGENTS.md regen skipped: .coding-os.yaml unreadable ({exc})")
        return notes
    agents = config.get("agents") or []
    templates = tuple(config.get("templates") or [])
    if not agents:
        notes.append("AGENTS.md regen skipped: no agents in .coding-os.yaml")
        return notes

    # Meta-repo dogfood guard (TASK-439): the coding-os source tree ships a
    # hand-written AGENTS.md (CLAUDE.md symlinks to it). A module toggle here
    # must still flip state + the runtime allowlist (done above), but must NOT
    # clobber the hand-written AGENTS.md with a generated one.
    from cli._init_helpers import is_coding_os_source_tree

    if is_coding_os_source_tree(project):
        notes.append("AGENTS.md skipped (coding-os meta-repo — hand-written content preserved)")
        return notes

    from cli.main import _build_world
    from cli.renderer import render_agents_md

    world = _build_world(agents[0], templates, project)
    new_content = render_agents_md(world, module_state(project))
    agents_md = project / "AGENTS.md"
    if agents_md.exists() and agents_md.read_text(encoding="utf-8") == new_content:
        notes.append("AGENTS.md unchanged")
        return notes
    if agents_md.exists():
        backup = agents_md.with_suffix(".md.bak")
        backup.write_text(agents_md.read_text(encoding="utf-8"), encoding="utf-8")
        notes.append(f"AGENTS.md backed up → {backup.name}")
    agents_md.write_text(new_content, encoding="utf-8")
    notes.append("AGENTS.md regenerated")
    return notes


def _cascade_skills_after_toggle(
    project: Path, module_id: str, enabled: bool, keep_skills: bool
) -> list[str]:
    """Relink/unlink the module's owned skills (TASK-475), meta-repo guarded.

    Best-effort: the state + allowlist + AGENTS.md are the load-bearing artifacts
    and have already committed by here; an idempotent symlink hiccup is a `cos
    doctor` (modules.skill_drift) follow-up, never a reason to fail the toggle."""
    from cli._init_helpers import is_coding_os_source_tree

    if is_coding_os_source_tree(project):
        return ["skills: cascade skipped (coding-os meta-repo — adapter links preserved)"]
    try:
        from cli.skill_commands import cascade_module_skills

        out = cascade_module_skills(project, module_id, enabled, keep_skills=keep_skills)
    except Exception as exc:  # noqa: BLE001 — toggle already committed; surface, don't fail
        return [f"skills: cascade skipped ({exc}) — run `cos doctor`"]
    notes: list[str] = []
    if out["unlinked"]:
        notes.append(f"skills unlinked (module off): {', '.join(out['unlinked'])}")
    if out["linked"]:
        notes.append(f"skills relinked: {', '.join(out['linked'])}")
    if keep_skills and out["kept"]:
        notes.append(f"skills kept linked (--keep-skills): {', '.join(out['kept'])}")
    return notes


def _installed_adapter_commands_dirs(project_root: Path) -> list[Path]:
    """Each installed adapter's commands dir (parity with the skills-dir scan in
    skill_commands._installed_adapter_skills_dirs)."""
    from cli._resources import adapters_dir
    from cli.adapter_registry import load_adapter_registry

    dirs: list[Path] = []
    for adapter in load_adapter_registry(adapters_dir()).values():
        commands_dir = getattr(adapter, "commands_dir", None)
        if not commands_dir:
            continue
        agent_dir = project_root / commands_dir
        if agent_dir.parent.is_dir():
            dirs.append(agent_dir)
    return dirs


def _toggle_command_link(project_root: Path, name: str, *, link: bool) -> int:
    """Link/unlink one core slash-command (`<name>.md`) in every adapter commands
    dir. Returns links touched; 0 when the command source is absent."""
    from cli._resources import core_dir

    source = core_dir("commands") / f"{name}.md"
    if not source.is_file():
        return 0
    touched = 0
    for commands_root in _installed_adapter_commands_dirs(project_root):
        link_path = commands_root / f"{name}.md"
        if link:
            commands_root.mkdir(parents=True, exist_ok=True)
            if link_path.is_symlink() and not link_path.exists():
                link_path.unlink()  # dangling link (target moved) — clear before relink
            if not link_path.exists():
                link_path.symlink_to(source)
                touched += 1
        elif link_path.is_symlink() or link_path.exists():
            link_path.unlink()
            touched += 1
    return touched


def cascade_module_commands(
    project_root: Path,
    module_id: str,
    enabled: bool,
    *,
    modules: dict | None = None,
) -> dict:
    """Relink/unlink a module's owned slash-commands after a module toggle —
    parity with cascade_module_skills. disable → unlink each owned command unless
    another enabled module still owns it (ref-count); enable → relink. Idempotent."""
    from cli.subsystems import load_subsystems, module_state

    modules = modules or load_subsystems()
    owned = sorted(modules[module_id].commands) if module_id in modules else []
    if not owned:
        return {"module": module_id, "linked": [], "unlinked": []}
    state = module_state(project_root, modules)
    still_owned = {
        cmd
        for mid, module in modules.items()
        if mid != module_id and state.get(mid, True)
        for cmd in module.commands
    }
    linked: list[str] = []
    unlinked: list[str] = []
    for name in owned:
        if name in still_owned:
            continue  # another enabled module still owns it — never unlink
        if _toggle_command_link(project_root, name, link=enabled):
            (linked if enabled else unlinked).append(name)
    return {"module": module_id, "linked": linked, "unlinked": unlinked}


def _cascade_commands_after_toggle(project: Path, module_id: str, enabled: bool) -> list[str]:
    """Relink/unlink the module's owned commands (TASK-481), meta-repo guarded.

    Best-effort like the skill cascade: state + allowlist already committed, so an
    idempotent symlink hiccup is a `cos doctor` (modules.command_drift) follow-up,
    never a reason to fail the toggle."""
    from cli._init_helpers import is_coding_os_source_tree

    if is_coding_os_source_tree(project):
        return ["commands: cascade skipped (coding-os meta-repo — adapter links preserved)"]
    try:
        out = cascade_module_commands(project, module_id, enabled)
    except Exception as exc:  # noqa: BLE001 — toggle already committed; surface, don't fail
        return [f"commands: cascade skipped ({exc}) — run `cos doctor`"]
    notes: list[str] = []
    if out["unlinked"]:
        notes.append(f"commands unlinked (module off): {', '.join(out['unlinked'])}")
    if out["linked"]:
        notes.append(f"commands relinked: {', '.join(out['linked'])}")
    return notes


def _installed_adapter_rules_dirs(project_root: Path) -> list[Path]:
    """Each rules-supporting adapter's rules dir (parity with the commands-dir scan)."""
    from cli._resources import adapters_dir
    from cli.adapter_registry import load_adapter_registry

    dirs: list[Path] = []
    for adapter in load_adapter_registry(adapters_dir()).values():
        if not getattr(adapter, "supports_rules", False):
            continue
        rules_dir = getattr(adapter, "rules_dir", None)
        if not rules_dir:
            continue
        agent_dir = project_root / rules_dir
        if agent_dir.parent.is_dir():
            dirs.append(agent_dir)
    return dirs


def _toggle_rule_link(project_root: Path, name: str, *, link: bool) -> int:
    """Link/unlink one core rule (`<name>`, e.g. memory.md) in every adapter rules
    dir. Returns links touched; 0 when the rule source is absent."""
    from cli._resources import core_dir

    source = core_dir("rules") / name
    if not source.is_file():
        return 0
    touched = 0
    for rules_root in _installed_adapter_rules_dirs(project_root):
        link_path = rules_root / name
        if link:
            rules_root.mkdir(parents=True, exist_ok=True)
            if link_path.is_symlink() and not link_path.exists():
                link_path.unlink()  # dangling link (target moved) — clear before relink
            if not link_path.exists():
                link_path.symlink_to(source)
                touched += 1
        elif link_path.is_symlink() or link_path.exists():
            link_path.unlink()
            touched += 1
    return touched


def cascade_module_rules(
    project_root: Path,
    module_id: str,
    enabled: bool,
    *,
    modules: dict | None = None,
) -> dict:
    """Relink/unlink a module's owned core rules after a module toggle — parity
    with cascade_module_commands. disable → unlink each owned rule unless another
    enabled module still owns it (ref-count); enable → relink. Idempotent."""
    from cli.subsystems import load_subsystems, module_state

    modules = modules or load_subsystems()
    owned = sorted(modules[module_id].rules) if module_id in modules else []
    if not owned:
        return {"module": module_id, "linked": [], "unlinked": []}
    state = module_state(project_root, modules)
    still_owned = {
        rule
        for mid, module in modules.items()
        if mid != module_id and state.get(mid, True)
        for rule in module.rules
    }
    linked: list[str] = []
    unlinked: list[str] = []
    for name in owned:
        if name in still_owned:
            continue  # another enabled module still owns it — never unlink
        if _toggle_rule_link(project_root, name, link=enabled):
            (linked if enabled else unlinked).append(name)
    return {"module": module_id, "linked": linked, "unlinked": unlinked}


def _cascade_rules_after_toggle(project: Path, module_id: str, enabled: bool) -> list[str]:
    """Relink/unlink the module's owned core rules (TASK-811), meta-repo guarded.

    Best-effort like the skill/command cascade: state + allowlist already committed,
    so an idempotent symlink hiccup is a `cos doctor` (modules.rule_drift) follow-up,
    never a reason to fail the toggle."""
    from cli._init_helpers import is_coding_os_source_tree

    if is_coding_os_source_tree(project):
        return ["rules: cascade skipped (coding-os meta-repo — adapter links preserved)"]
    try:
        out = cascade_module_rules(project, module_id, enabled)
    except Exception as exc:  # noqa: BLE001 — toggle already committed; surface, don't fail
        return [f"rules: cascade skipped ({exc}) — run `cos doctor`"]
    notes: list[str] = []
    if out["unlinked"]:
        notes.append(f"rules unlinked (module off): {', '.join(out['unlinked'])}")
    if out["linked"]:
        notes.append(f"rules relinked: {', '.join(out['linked'])}")
    return notes


def sync_module_docs(
    project: Path, templates: tuple[str, ...], module_id: str, enabled: bool
) -> dict:
    """Prune (disable) / restore (enable) a module's `| module:X`-tagged scaffold
    docs on a live toggle. Disable moves each present doc to
    .coding-os/pruned-docs/<rel> (always backed up — never destructive); enable
    moves any backup back. Idempotent — a doc is tagged by exactly one module."""
    from cli.main import module_scaffold_doc_rels

    rels = module_scaffold_doc_rels(tuple(templates), module_id)
    if not rels:
        return {"module": module_id, "pruned": [], "restored": []}
    backup_root = project / ".coding-os" / "pruned-docs"
    pruned: list[str] = []
    restored: list[str] = []
    for rel in rels:
        dest = project / rel
        backup = backup_root / rel
        if enabled:
            if backup.is_file() and not dest.exists():
                dest.parent.mkdir(parents=True, exist_ok=True)
                backup.replace(dest)
                restored.append(rel)
        elif dest.is_file():
            backup.parent.mkdir(parents=True, exist_ok=True)
            dest.replace(backup)
            pruned.append(rel)
    return {"module": module_id, "pruned": pruned, "restored": restored}


def _sync_module_docs_after_toggle(project: Path, module_id: str, enabled: bool) -> list[str]:
    """Prune/restore the module's tagged scaffold docs (TASK-813), meta-repo guarded.

    Best-effort like the other cascades; pruned docs are backed up under
    .coding-os/pruned-docs/, so a hiccup is a `cos doctor` (modules.doc_drift)
    follow-up, never data loss or a reason to fail the toggle."""
    from cli._init_helpers import is_coding_os_source_tree

    if is_coding_os_source_tree(project):
        return ["docs: sync skipped (coding-os meta-repo — scaffold docs are the source)"]
    try:
        import yaml as _yaml

        config = _yaml.safe_load((project / ".coding-os.yaml").read_text(encoding="utf-8")) or {}
        templates = tuple(config.get("templates") or [])
        out = sync_module_docs(project, templates, module_id, enabled)
    except Exception as exc:  # noqa: BLE001 — toggle already committed; surface, don't fail
        return [f"docs: sync skipped ({exc}) — run `cos doctor`"]
    notes: list[str] = []
    if out["pruned"]:
        notes.append(f"docs pruned (module off, backed up): {', '.join(out['pruned'])}")
    if out["restored"]:
        notes.append(f"docs restored (module on): {', '.join(out['restored'])}")
    return notes


def toggle_and_regen(
    project: Path, module_id: str, enabled: bool, *, keep_skills: bool = False
) -> tuple[ToggleResult, list[str]]:
    """Single entry point shared by the CLI and the hub settings route.

    Atomic: a regen failure rolls the state flip back, so the project never
    lands in a half state (state says disabled, artifacts say enabled)."""
    result = set_module_enabled(project, module_id, enabled)
    if not result.ok:
        logger.warning("module toggle refused for '%s': %s", module_id, result.reason)
        return result, []
    try:
        notes = regen_after_toggle(project)
    except Exception as exc:
        logger.warning(
            "module toggle regen failed for '%s' — rolling back state + allowlist: %s",
            module_id,
            exc,
        )
        # Roll back the state flip AND re-derive the runtime allowlist. regen
        # writes the allowlist FIRST (it can't know the later AGENTS.md render
        # will throw), so reverting only the state file would strand the
        # allowlist on the failed-toggle state — an inverted half-state where
        # state says enabled but the module's hooks are still listed disabled.
        # (audit pass-4 #10)
        set_module_enabled(project, module_id, not enabled)
        from cli.project_overrides import write_runtime_allowlist

        try:
            write_runtime_allowlist(project)
        except Exception as restore_exc:  # noqa: BLE001 — original error wins; surface both
            return (
                ToggleResult(
                    ok=False,
                    module_id=module_id,
                    reason=(
                        f"regen failed ({exc}); allowlist restore also failed "
                        f"({restore_exc}) — run `cos doctor` to reconcile"
                    ),
                ),
                [],
            )
        return (
            ToggleResult(
                ok=False,
                module_id=module_id,
                reason=f"regen failed ({exc}) — module state + runtime allowlist rolled back",
            ),
            [],
        )
    notes.extend(_cascade_skills_after_toggle(project, module_id, enabled, keep_skills))
    notes.extend(_cascade_commands_after_toggle(project, module_id, enabled))
    notes.extend(_cascade_rules_after_toggle(project, module_id, enabled))
    notes.extend(_sync_module_docs_after_toggle(project, module_id, enabled))
    return result, notes


def module_state_payload(project: Path) -> dict:
    """Serializable per-module state — shared by `cos module list --format json`
    and GET /api/settings/modules (same SSOT, api-contract-discipline)."""
    modules = load_subsystems()
    state = module_state(project, modules)
    return {
        "modules": [
            {
                "id": m.id,
                "label": m.label,
                "hint": m.hint,
                "kernel": m.kernel,
                "enabled": state[m.id],
                "depends_on": list(m.depends_on),
                "hooks": len(m.hooks),
                "tools": len(m.tools),
                "skills": len(m.skills),
                "rules": len(m.rules),
                "commands": len(m.commands),
                "depends_on_reason": m.depends_on_reason,
                "owned": {
                    "hooks": list(m.hooks),
                    "tools": list(m.tools),
                    "skills": list(m.skills),
                    "commands": list(m.commands),
                    "rules": list(m.rules),
                },
            }
            for m in modules.values()
            if not m.hidden
        ]
    }


@click.group("module")
def module_group() -> None:
    """Inspect and toggle subsystem modules (docs, tasks, graph, memory, …)."""


@module_group.command("list")
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
def module_list(output_format: str) -> None:
    """Show per-module state with dependencies."""
    project = _project_root()
    payload = module_state_payload(project)
    if output_format == "json":
        click.echo(json.dumps(payload, indent=2))
        return
    for m in payload["modules"]:
        flag = "kernel (always on)" if m["kernel"] else ("enabled" if m["enabled"] else "DISABLED")
        deps = f"  needs: {', '.join(m['depends_on'])}" if m["depends_on"] else ""
        click.echo(
            f"  {m['id']:<12} {flag:<18} hooks={m['hooks']} tools={m['tools']} "
            f"skills={m['skills']}{deps}"
        )


def _run_toggle(module_id: str, enabled: bool, *, keep_skills: bool = False) -> None:
    project = _project_root()
    result, notes = toggle_and_regen(project, module_id, enabled, keep_skills=keep_skills)
    if not result.ok:
        raise click.ClickException(result.reason)
    click.echo(f"module '{module_id}' {'enabled' if enabled else 'disabled'}")
    for note in notes:
        click.echo(f"  {note}")


@module_group.command("enable")
@click.argument("module_id")
def module_enable(module_id: str) -> None:
    """Enable a module and regenerate dependent artifacts (relinks its skills)."""
    _run_toggle(module_id, True)


@module_group.command("disable")
@click.argument("module_id")
@click.option(
    "--keep-skills",
    is_flag=True,
    default=False,
    help="Disable the module but keep its skills linked (skip the skill cascade).",
)
@click.option(
    "--yes", "-y", is_flag=True, default=False, help="Skip the skill-unlink confirmation."
)
def module_disable(module_id: str, keep_skills: bool, yes: bool) -> None:
    """Disable a module and regenerate dependent artifacts (unlinks its skills)."""
    import sys

    if not keep_skills and not yes and sys.stdin.isatty():
        from cli.skill_commands import planned_skill_unlinks

        unlinks = planned_skill_unlinks(_project_root(), module_id)
        if unlinks and not click.confirm(
            f"Disabling '{module_id}' will unlink skill(s): {', '.join(unlinks)}. Continue?",
            default=True,
        ):
            raise click.ClickException("aborted — module left enabled")
    _run_toggle(module_id, False, keep_skills=keep_skills)
