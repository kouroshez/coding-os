"""`cos add-stack <id>` — add a stack module to an already-initialized project.

Design (see plan §2.3):

1. Load the project config. Check the project has been initialized.
2. If the stack is already installed → idempotent skip with INFO.
3. Apply the stack template (copy files into .coding-os/templates/<id>).
4. Overlay scaffold docs from src/templates/<id>/scaffold/ (never overwriting
   existing project files).
5. Rebuild the AggregatedWorld including the new stack.
6. Regenerate AGENTS.md diff-safely:
     - identical to existing → silent replace
     - drift detected without --regen-agents-md → WARN, backup + skip
     - with --regen-agents-md → backup old file to
       .coding-os/backups/AGENTS.md.<ts>.bak and write new content
7. Update .coding-os.yaml::templates and append stack_history entry.
8. Print summary (text or JSON).
"""

from __future__ import annotations

import contextlib
import datetime as _dt
import io
import json
from pathlib import Path

import click
import yaml

from cli._data_types import AggregatedWorld
from cli._resources import overlay_adapter_dirs, overlay_template_dirs
from cli.adapter_registry import load_adapter_registry
from cli.aggregator import aggregate, today_iso
from cli.renderer import render_agents_md
from cli.stack_registry import load_base_profile, load_stack_registry

CODING_OS_ROOT = Path(__file__).resolve().parent.parent.parent
TEMPLATES_DIR = CODING_OS_ROOT / "src" / "templates"
ADAPTERS_DIR = CODING_OS_ROOT / "src" / "adapters"
CONFIG_FILE = ".coding-os.yaml"
STATE_DIR = ".coding-os"


class AddStackError(click.ClickException):
    """Non-zero exit for add-stack errors."""


def _load_project_config(project: Path) -> dict:
    config_path = project / CONFIG_FILE
    if not config_path.exists():
        raise AddStackError(f"{CONFIG_FILE} not found in {project} — run `cos init` first")
    try:
        return yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise AddStackError(f"invalid {CONFIG_FILE}: {exc}") from exc


def _save_project_config(project: Path, config: dict) -> None:
    (project / CONFIG_FILE).write_text(
        yaml.dump(config, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )


def _apply_stack_files(stack_profile, project: Path, agent: str) -> None:
    """Copy per-stack files (skills, rules, hooks, playbooks) into state dir.

    Reuses cli.main._apply_template — it handles both the state-dir mirror
    AND the adapter's rules_dir copy when the adapter supports path-scoped
    rules.
    """
    from cli.main import _apply_template  # late import to avoid cycle

    _apply_template(stack_profile.id, project, agent=agent)


def _overlay_stack_scaffold(stack_profile, project: Path, substitutions: dict[str, str]) -> int:
    """Copy src/templates/<stack>/scaffold/* into the project root.

    Idempotent: existing files are never overwritten. Markdown files have
    `{{KEY}}` placeholders resolved.
    """
    from cli.main import _overlay_scaffold  # late import

    # _overlay_scaffold expects a tuple of template names; we pass only the
    # new stack. It internally also overlays _base/scaffold, but since base
    # scaffold was already applied at init time and is idempotent, this is
    # safe.
    return _overlay_scaffold(project, (stack_profile.id,), substitutions)


def _backup_agents_md(project: Path) -> Path:
    """Copy current AGENTS.md into <project>/.coding-os/backups/AGENTS.md.<ts>.bak.

    Caller must have verified AGENTS.md exists — we assert it.
    """
    agents_md = project / "AGENTS.md"
    assert agents_md.exists(), "AGENTS.md must exist before backup"
    ts = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_dir = project / STATE_DIR / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"AGENTS.md.{ts}.bak"
    backup_path.write_text(
        agents_md.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    return backup_path


def _append_stack_history(config: dict, stack_id: str) -> None:
    history = config.setdefault("stack_history", [])
    history.append(
        {
            "stack_id": stack_id,
            "added_at": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
    )


def _build_summary(
    *,
    project: Path,
    stack_id: str,
    already_installed: bool,
    agents_md_changed: bool,
    agents_md_backup: Path | None,
    files_copied: int,
    conflicts: tuple[str, ...],
) -> dict:
    return {
        "status": "noop" if already_installed else "ok",
        "project": str(project),
        "stack_id": stack_id,
        "already_installed": already_installed,
        "agents_md_changed": agents_md_changed,
        "agents_md_backup": str(agents_md_backup) if agents_md_backup else None,
        "files_copied": files_copied,
        "conflicts": list(conflicts),
    }


def _print_text(summary: dict) -> None:
    if summary["status"] == "noop":
        click.echo(f"Stack '{summary['stack_id']}' already installed (idempotent skip).")
        return
    click.echo(f"Added stack '{summary['stack_id']}' to {summary['project']}")
    click.echo(f"  Files copied: {summary['files_copied']}")
    if summary["agents_md_changed"]:
        click.echo("  AGENTS.md: regenerated")
        if summary["agents_md_backup"]:
            click.echo(f"  AGENTS.md backup: {summary['agents_md_backup']}")
    else:
        click.echo("  AGENTS.md: unchanged")
    for warning in summary["conflicts"]:
        click.echo(f"  WARN: {warning}", err=True)


@click.command("add-stack")
@click.argument("stack_id")
@click.option("--project-dir", "-d", default=".", help="Project directory")
@click.option(
    "--regen-agents-md/--no-regen-agents-md",
    default=True,
    help="Regenerate AGENTS.md to reflect the new stack (default: yes). A backup is created first.",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Output format",
)
def add_stack(
    stack_id: str,
    project_dir: str,
    regen_agents_md: bool,
    output_format: str,
) -> None:
    """Add a stack module to an initialized project."""
    project = Path(project_dir).resolve()
    config = _load_project_config(project)

    # 1. Registry lookup (consumer-discovery: include community overlay stacks)
    stacks = load_stack_registry(TEMPLATES_DIR, overlay_dirs=overlay_template_dirs())
    if stack_id not in stacks:
        raise AddStackError(f"stack '{stack_id}' not found — available: {sorted(stacks.keys())}")
    stack_profile = stacks[stack_id]

    installed_templates = list(config.get("templates") or [])
    already_installed = stack_id in installed_templates

    if already_installed:
        summary = _build_summary(
            project=project,
            stack_id=stack_id,
            already_installed=True,
            agents_md_changed=False,
            agents_md_backup=None,
            files_copied=0,
            conflicts=(),
        )
        if output_format == "json":
            click.echo(json.dumps(summary, indent=2))
        else:
            _print_text(summary)
        return

    # 2. Apply stack files + scaffold overlay.
    # Compute world WITH the new stack so substitutions reflect the final
    # state for both scaffold overlay and AGENTS.md rendering.
    agent = (config.get("agents") or [None])[0]
    if not agent:
        raise AddStackError("no agent recorded in .coding-os.yaml")

    adapters = load_adapter_registry(ADAPTERS_DIR, overlay_dirs=overlay_adapter_dirs())
    if agent not in adapters:
        raise AddStackError(f"adapter '{agent}' not in registry")
    adapter_profile = adapters[agent]
    base = load_base_profile(TEMPLATES_DIR / "_base")

    new_stack_list = [*installed_templates, stack_id]
    stack_profiles = []
    for s in new_stack_list:
        if s not in stacks:
            click.echo(
                f"  WARN: stack '{s}' recorded in config but not found in "
                f"src/templates/*/stack.yaml — skipping",
                err=True,
            )
            continue
        stack_profiles.append(stacks[s])
    world: AggregatedWorld = aggregate(
        base,
        stack_profiles,
        adapter_profile,
        project.name,
        today=today_iso(),
    )

    # In JSON mode, silence the chatty scaffold output so the final
    # stdout is pure parseable JSON.
    _silencer = (
        contextlib.redirect_stdout(io.StringIO())
        if output_format == "json"
        else contextlib.nullcontext()
    )
    with _silencer:
        _apply_stack_files(stack_profile, project, agent)
        files_copied = _overlay_stack_scaffold(stack_profile, project, world.substitutions)
        # Re-compose .coding-os/ configs to fold in the new stack — merge its
        # overlay onto the existing composed files so the board/RAG gain its
        # swimlanes/sources, preserving user edits (config-composition.md).
        from cli.config_composer import recompose_for_added_stack

        recompose_for_added_stack(
            project, project / STATE_DIR, stack_profile.id, templates_dir=TEMPLATES_DIR
        )
        # Link the new stack's skills into the adapter's skills_dir.
        # `cos init` does this via _run_scaffold_phase step 5b; `cos add-stack`
        # bypasses that path so we must link here to keep the adapter's
        # Skill tool surface in sync with installed templates.
        from cli.main import _link_stack_skills  # late import to avoid cycle

        _link_stack_skills(agent, (stack_id,), project)

    # 3. Diff-safe AGENTS.md regeneration.
    from cli._init_helpers import is_coding_os_source_tree
    from cli.subsystems import module_state

    agents_md = project / "AGENTS.md"
    new_content = render_agents_md(world, module_state(project))
    agents_md_changed = False
    agents_md_backup: Path | None = None

    # Meta-repo dogfood guard (F15): never clobber the hand-written source-tree
    # AGENTS.md (parity with the module-toggle guard).
    if is_coding_os_source_tree(project):
        click.echo("  INFO: AGENTS.md skipped (coding-os meta-repo)", err=True)
    elif not agents_md.exists():
        agents_md.write_text(new_content, encoding="utf-8")
        agents_md_changed = True
    else:
        old_content = agents_md.read_text(encoding="utf-8")
        if old_content == new_content:
            pass  # nothing to do
        elif regen_agents_md:
            agents_md_backup = _backup_agents_md(project)
            agents_md.write_text(new_content, encoding="utf-8")
            agents_md_changed = True
        else:
            click.echo(
                "  INFO: AGENTS.md not regenerated (--no-regen-agents-md set). "
                "Run with --regen-agents-md to refresh it.",
                err=True,
            )

    # 4. Update config
    config["templates"] = new_stack_list
    _append_stack_history(config, stack_id)
    _save_project_config(project, config)

    summary = _build_summary(
        project=project,
        stack_id=stack_id,
        already_installed=False,
        agents_md_changed=agents_md_changed,
        agents_md_backup=agents_md_backup,
        files_copied=files_copied,
        conflicts=world.conflicts,
    )
    if output_format == "json":
        click.echo(json.dumps(summary, indent=2))
    else:
        _print_text(summary)
