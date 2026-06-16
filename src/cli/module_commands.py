"""`cos module list|enable|disable` — subsystem toggles + dependent regen (TASK-354).

Wraps cli.subsystems (the state SSOT, TASK-349). A successful toggle
regenerates everything the module state feeds: AGENTS.md (conditional
sections, TASK-353) and the runtime hook allowlist (TASK-256/353).
"""

from __future__ import annotations

import json
from pathlib import Path

import click

from cli.subsystems import ToggleResult, load_subsystems, module_state, set_module_enabled


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
    # clobber the hand-written AGENTS.md with a generated one. Detect the
    # source-tree markers (same signature as _refuse_coding_os_self_init) and
    # skip only the AGENTS.md rewrite.
    if (project / "src" / "core" / "thinking_os" / "server.py").exists() and (
        project / "src" / "cli" / "main.py"
    ).exists():
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


def toggle_and_regen(project: Path, module_id: str, enabled: bool) -> tuple[ToggleResult, list[str]]:
    """Single entry point shared by the CLI and the hub settings route.

    Atomic: a regen failure rolls the state flip back, so the project never
    lands in a half state (state says disabled, artifacts say enabled)."""
    result = set_module_enabled(project, module_id, enabled)
    if not result.ok:
        return result, []
    try:
        notes = regen_after_toggle(project)
    except Exception as exc:
        set_module_enabled(project, module_id, not enabled)
        return (
            ToggleResult(
                ok=False,
                module_id=module_id,
                reason=f"regen failed ({exc}) — module state rolled back, nothing changed",
            ),
            [],
        )
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
                "kernel": m.kernel,
                "enabled": state[m.id],
                "depends_on": list(m.depends_on),
                "hooks": len(m.hooks),
                "tools": len(m.tools),
            }
            for m in modules.values()
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
        click.echo(f"  {m['id']:<12} {flag:<18} hooks={m['hooks']} tools={m['tools']}{deps}")


def _run_toggle(module_id: str, enabled: bool) -> None:
    project = _project_root()
    result, notes = toggle_and_regen(project, module_id, enabled)
    if not result.ok:
        raise click.ClickException(result.reason)
    click.echo(f"module '{module_id}' {'enabled' if enabled else 'disabled'}")
    for note in notes:
        click.echo(f"  {note}")


@module_group.command("enable")
@click.argument("module_id")
def module_enable(module_id: str) -> None:
    """Enable a module and regenerate dependent artifacts."""
    _run_toggle(module_id, True)


@module_group.command("disable")
@click.argument("module_id")
def module_disable(module_id: str) -> None:
    """Disable a module and regenerate dependent artifacts."""
    _run_toggle(module_id, False)
