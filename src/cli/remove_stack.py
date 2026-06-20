"""`cos remove-stack <id>` — the inverse of `cos add-stack`.

Reverses every side effect `add-stack` produced for one stack:

1. Load the project config; idempotent skip with INFO when the stack is not
   installed.
2. Back up `.coding-os.yaml` and the composed `.coding-os/*` configs before any
   mutation (removal recomposes from base + remaining stacks, which discards
   user edits layered onto those files — the backup is the recovery path).
3. Recompose `.coding-os/{rag-config.yaml,scrumban-config.yaml,domain-config.json}`
   from base + the REMAINING stacks (drops the removed stack's contribution).
4. Unlink the removed stack's skills from the adapter's skills dir — but only
   skills that no remaining stack still provides.
5. Remove the removed stack's path-scoped rule files
   (`<rules_dir>/<stack>-*.md`) that add-stack copied, and its
   `.coding-os/templates/<stack>/` mirror, so no orphaned artifact remains.
6. Regenerate AGENTS.md diff-safely (backup + write, or skip with
   --no-regen-agents-md).
7. Drop the stack from `.coding-os.yaml::templates` (comment-preserving line
   edit) and append a `stack_history` removal entry.
8. Print summary (text or JSON).
"""

from __future__ import annotations

import contextlib
import datetime as _dt
import io
import json
import re
import shutil
from pathlib import Path

import click
import yaml

from cli._data_types import AggregatedWorld
from cli._resources import overlay_adapter_dirs, overlay_template_dirs
from cli.adapter_registry import load_adapter_registry
from cli.aggregator import aggregate, today_iso
from cli.config_composer import recompose_for_removed_stack
from cli.renderer import render_agents_md
from cli.stack_registry import load_base_profile, load_stack_registry

CODING_OS_ROOT = Path(__file__).resolve().parent.parent.parent
TEMPLATES_DIR = CODING_OS_ROOT / "src" / "templates"
ADAPTERS_DIR = CODING_OS_ROOT / "src" / "adapters"
CONFIG_FILE = ".coding-os.yaml"
STATE_DIR = ".coding-os"
_COMPOSED_CONFIGS = ("rag-config.yaml", "scrumban-config.yaml", "domain-config.json")


class RemoveStackError(click.ClickException):
    """Non-zero exit for remove-stack errors."""


def _load_project_config(project: Path) -> dict:
    config_path = project / CONFIG_FILE
    if not config_path.exists():
        raise RemoveStackError(f"{CONFIG_FILE} not found in {project} — run `cos init` first")
    try:
        return yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise RemoveStackError(f"invalid {CONFIG_FILE}: {exc}") from exc


def _backup_file(project: Path, relative: Path) -> Path:
    """Copy a project file into `.coding-os/backups/<name>.<ts>.bak`, return path."""
    src = project / relative
    assert src.exists(), f"{relative} must exist before backup"
    ts = _dt.datetime.now().strftime("%Y%m%dT%H%M%S")
    backup_dir = project / STATE_DIR / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"{src.name}.{ts}.bak"
    backup_path.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    return backup_path


def _rewrite_templates_block(raw: str, stack_id: str) -> str:
    """Drop the `- <stack_id>` item from the block-style `templates:` list.

    Comment-preserving: edits only the matched list-item line, leaving every
    other line (and its comments) byte-for-byte intact. Handles both the
    PyYAML-dumped flush form (`- meta`) and the conventional indented form
    (`  - meta`). Quoted scalars (`- "meta"`) are matched too.
    """
    lines = raw.splitlines(keepends=True)
    out: list[str] = []
    in_block = False
    item_re = re.compile(r"^(\s*)-\s+(?P<val>.+?)\s*$")
    for line in lines:
        stripped = line.rstrip("\n")
        if not in_block:
            if re.match(r"^templates:\s*$", stripped):
                in_block = True
            out.append(line)
            continue
        # Inside the templates block: a list item starts with optional indent + "- ".
        m = item_re.match(stripped)
        if m is not None:
            val = m.group("val").strip().strip("'\"")
            if val == stack_id:
                continue  # drop this line — the removal
            out.append(line)
            continue
        # A blank line inside a block is tolerated (skip, keep scanning).
        if stripped.strip() == "":
            out.append(line)
            continue
        # Any non-item, non-blank line ends the templates block.
        in_block = False
        out.append(line)
    return "".join(out)


def _append_stack_history_block(raw: str, stack_id: str) -> str:
    """Append a `stack_history` removal entry, comment-preserving.

    Reuses the existing `stack_history:` block when present (appends two indented
    lines after the last list item); otherwise opens a fresh block at EOF. Never
    touches unrelated lines, so comments are preserved.
    """
    removed_at = _dt.datetime.now().isoformat(timespec="seconds")
    entry_lines = [
        f"- stack_id: {stack_id}\n",
        f"  removed_at: '{removed_at}'\n",
    ]
    lines = raw.splitlines(keepends=True)
    history_start = None
    for i, line in enumerate(lines):
        if re.match(r"^stack_history:\s*$", line.rstrip("\n")):
            history_start = i
            break

    if history_start is None:
        # No block yet — open one at EOF (ensure a trailing newline first).
        suffix = "" if raw.endswith("\n") or raw == "" else "\n"
        return raw + suffix + "stack_history:\n" + "".join(entry_lines)

    # Find the end of the existing block (first line at column 0 after the header,
    # or EOF) and splice the new entry in just before it.
    insert_at = len(lines)
    for j in range(history_start + 1, len(lines)):
        body = lines[j].rstrip("\n")
        if body == "":
            continue
        if not body.startswith((" ", "\t", "-")):
            insert_at = j
            break
    new_lines = lines[:insert_at] + entry_lines + lines[insert_at:]
    return "".join(new_lines)


def _update_config_file(project: Path, stack_id: str) -> None:
    """Drop the stack from `templates` and log a removal in `stack_history`.

    Done as a comment-preserving text edit (not a yaml.dump round-trip) so the
    consumer's hand-written comments in `.coding-os.yaml` survive removal.
    """
    config_path = project / CONFIG_FILE
    raw = config_path.read_text(encoding="utf-8")
    raw = _rewrite_templates_block(raw, stack_id)
    raw = _append_stack_history_block(raw, stack_id)
    config_path.write_text(raw, encoding="utf-8")


def _skills_provided_by(stack_id: str) -> set[str]:
    """Skill dir names shipped by a stack's `src/templates/<stack>/skills/`."""
    skills_dir = TEMPLATES_DIR / stack_id / "skills"
    if not skills_dir.is_dir():
        return set()
    return {p.name for p in skills_dir.iterdir() if p.is_dir() and (p / "SKILL.md").is_file()}


def _unlink_stack_skills(
    agent: str,
    stack_id: str,
    remaining_templates: tuple[str, ...],
    project: Path,
) -> tuple[str, ...]:
    """Remove the removed stack's skill links not still provided by another stack.

    Returns the tuple of skill names actually unlinked. No-op for adapters whose
    skills_dir is null (e.g. Codex).
    """
    adapters = load_adapter_registry(ADAPTERS_DIR, overlay_dirs=overlay_adapter_dirs())
    if agent not in adapters:
        return ()
    skills_dir_rel = adapters[agent].skills_dir
    if not skills_dir_rel:
        return ()
    skills_dir = project / skills_dir_rel
    if not skills_dir.is_dir():
        return ()

    removed_skills = _skills_provided_by(stack_id)
    if not removed_skills:
        return ()
    still_provided: set[str] = set()
    for other in remaining_templates:
        still_provided |= _skills_provided_by(other)

    unlinked: list[str] = []
    for name in sorted(removed_skills - still_provided):
        link_parent = skills_dir / name
        if link_parent.exists() or link_parent.is_symlink():
            shutil.rmtree(link_parent, ignore_errors=True)
            unlinked.append(name)
    return tuple(unlinked)


def _remove_stack_rules(agent: str, stack_id: str, project: Path) -> int:
    """Delete path-scoped rule files add-stack copied as `<stack>-*.md`. Returns count."""
    adapters = load_adapter_registry(ADAPTERS_DIR, overlay_dirs=overlay_adapter_dirs())
    if agent not in adapters:
        return 0
    adapter_profile = adapters[agent]
    if not (adapter_profile.supports_rules and adapter_profile.rules_dir):
        return 0
    rules_dir = project / adapter_profile.rules_dir
    if not rules_dir.is_dir():
        return 0
    removed = 0
    for rule_file in sorted(rules_dir.glob(f"{stack_id}-*.md")):
        rule_file.unlink()
        removed += 1
    return removed


def _remove_template_mirror(stack_id: str, project: Path) -> bool:
    """Remove `.coding-os/src/templates/<stack>/` mirror copied by add-stack."""
    mirror = project / STATE_DIR / "src" / "templates" / stack_id
    if mirror.is_dir():
        shutil.rmtree(mirror, ignore_errors=True)
        return True
    return False


def _build_summary(
    *,
    project: Path,
    stack_id: str,
    not_installed: bool,
    agents_md_changed: bool,
    agents_md_backup: Path | None,
    config_backup: Path | None,
    recomposed: tuple[str, ...],
    unlinked_skills: tuple[str, ...],
    rules_removed: int,
) -> dict:
    return {
        "status": "noop" if not_installed else "ok",
        "project": str(project),
        "stack_id": stack_id,
        "not_installed": not_installed,
        "agents_md_changed": agents_md_changed,
        "agents_md_backup": str(agents_md_backup) if agents_md_backup else None,
        "config_backup": str(config_backup) if config_backup else None,
        "recomposed_configs": list(recomposed),
        "unlinked_skills": list(unlinked_skills),
        "rules_removed": rules_removed,
    }


def _print_text(summary: dict) -> None:
    if summary["status"] == "noop":
        click.echo(f"Stack '{summary['stack_id']}' is not installed (nothing to remove).")
        return
    click.echo(f"Removed stack '{summary['stack_id']}' from {summary['project']}")
    if summary["recomposed_configs"]:
        click.echo(f"  Recomposed configs: {', '.join(summary['recomposed_configs'])}")
    if summary["unlinked_skills"]:
        click.echo(f"  Unlinked skills: {', '.join(summary['unlinked_skills'])}")
    if summary["rules_removed"]:
        click.echo(f"  Removed path-scoped rules: {summary['rules_removed']}")
    if summary["agents_md_changed"]:
        click.echo("  AGENTS.md: regenerated")
        if summary["agents_md_backup"]:
            click.echo(f"  AGENTS.md backup: {summary['agents_md_backup']}")
    else:
        click.echo("  AGENTS.md: unchanged")
    if summary["config_backup"]:
        click.echo(f"  Config backup: {summary['config_backup']}")


@click.command("remove-stack")
@click.argument("stack_id")
@click.option("--project-dir", "-d", default=".", help="Project directory")
@click.option(
    "--regen-agents-md/--no-regen-agents-md",
    default=True,
    help="Regenerate AGENTS.md to drop the stack (default: yes). A backup is created first.",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Output format",
)
def remove_stack(
    stack_id: str,
    project_dir: str,
    regen_agents_md: bool,
    output_format: str,
) -> None:
    """Remove a stack module from a project (reverse of add-stack)."""
    project = Path(project_dir).resolve()
    config = _load_project_config(project)

    installed_templates = list(config.get("templates") or [])
    if stack_id not in installed_templates:
        summary = _build_summary(
            project=project,
            stack_id=stack_id,
            not_installed=True,
            agents_md_changed=False,
            agents_md_backup=None,
            config_backup=None,
            recomposed=(),
            unlinked_skills=(),
            rules_removed=0,
        )
        if output_format == "json":
            click.echo(json.dumps(summary, indent=2))
        else:
            _print_text(summary)
        return

    agent = (config.get("agents") or [None])[0]
    if not agent:
        raise RemoveStackError("no agent recorded in .coding-os.yaml")

    adapters = load_adapter_registry(ADAPTERS_DIR, overlay_dirs=overlay_adapter_dirs())
    if agent not in adapters:
        raise RemoveStackError(f"adapter '{agent}' not in registry")
    adapter_profile = adapters[agent]
    base = load_base_profile(TEMPLATES_DIR / "_base")
    stacks = load_stack_registry(TEMPLATES_DIR, overlay_dirs=overlay_template_dirs())

    remaining_templates = tuple(s for s in installed_templates if s != stack_id)

    # Build the world WITHOUT the removed stack so AGENTS.md reflects the final
    # state. Skip config-only stacks that lack a stack.yaml (mirrors add-stack).
    stack_profiles = []
    for s in remaining_templates:
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

    # Back up the config before mutating it.
    config_backup = _backup_file(project, Path(CONFIG_FILE))

    # Back up each composed config that exists before recompose discards edits.
    state_dir = project / STATE_DIR
    for name in _COMPOSED_CONFIGS:
        if (state_dir / name).is_file():
            _backup_file(project, Path(STATE_DIR) / name)

    _silencer = (
        contextlib.redirect_stdout(io.StringIO())
        if output_format == "json"
        else contextlib.nullcontext()
    )
    with _silencer:
        recomposed = tuple(
            recompose_for_removed_stack(
                project, state_dir, list(remaining_templates), templates_dir=TEMPLATES_DIR
            )
        )
        unlinked_skills = _unlink_stack_skills(agent, stack_id, remaining_templates, project)
        rules_removed = _remove_stack_rules(agent, stack_id, project)
        _remove_template_mirror(stack_id, project)

    # Diff-safe AGENTS.md regeneration.
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
            pass
        elif regen_agents_md:
            agents_md_backup = _backup_file(project, Path("AGENTS.md"))
            agents_md.write_text(new_content, encoding="utf-8")
            agents_md_changed = True
        else:
            click.echo(
                "  INFO: AGENTS.md not regenerated (--no-regen-agents-md set). "
                "Run with --regen-agents-md to refresh it.",
                err=True,
            )

    # Update config last (comment-preserving): drop from templates + log removal.
    _update_config_file(project, stack_id)

    summary = _build_summary(
        project=project,
        stack_id=stack_id,
        not_installed=False,
        agents_md_changed=agents_md_changed,
        agents_md_backup=agents_md_backup,
        config_backup=config_backup,
        recomposed=recomposed,
        unlinked_skills=unlinked_skills,
        rules_removed=rules_removed,
    )
    if output_format == "json":
        click.echo(json.dumps(summary, indent=2))
    else:
        _print_text(summary)
