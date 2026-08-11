"""`cos module` — core-rule symlink cascade after a subsystem toggle (TASK-811)."""

from __future__ import annotations

from pathlib import Path


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
    except Exception as exc:
        return [f"rules: cascade skipped ({exc}) — run `cos doctor`"]
    notes: list[str] = []
    if out["unlinked"]:
        notes.append(f"rules unlinked (module off): {', '.join(out['unlinked'])}")
    if out["linked"]:
        notes.append(f"rules relinked: {', '.join(out['linked'])}")
    return notes
