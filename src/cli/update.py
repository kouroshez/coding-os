"""`cos update` — re-link assets + run DB migrations for an existing project.

Design (plan D.3):
  1. Detect existing `.coding-os.yaml` — error if missing.
  2. Build current project manifest: which symlinks/files exist, with targets.
  3. Build target manifest from CODING_OS_ROOT for the declared agent+stacks.
  4. Compute diff (added, removed, changed).
  5. Show diff. Unless --dry-run, apply:
       - add missing symlinks
       - remove orphan symlinks (target no longer in source)
       - run DB migrations (idempotent — init_db applies new versions)
  6. Write .coding-os/installed-manifest.json snapshot.

Non-destructive: never touches docs/, AGENTS.md, .coding-os.yaml user fields,
or anything that isn't a managed symlink/asset.
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

import click
import yaml

logger = logging.getLogger(__name__)

from cli._init_helpers import ensure_agents_md, materialize_makefile_targets
from cli._resources import adapters_dir, core_dir, data_root, templates_dir
from cli.adapter_registry import load_adapter_registry
from cli.aggregator import aggregate, today_iso
from cli.core_version import current_core_version, read_stamped_version, stamp_core_version
from cli.stack_registry import (
    load_base_profile,
    load_stack_registry,
    resolve_relocated_profiles,
)
from cli.sync_all import _dangling, _iter_symlinks, _prune_dangling

# Resolved via importlib (TASK-219) so update works under both a src-layout
# editable install and a built wheel — and keeps working after the meta-repo
# is moved and reinstalled. CODING_OS_ROOT is informational (installed-manifest).
CODING_OS_ROOT = data_root().parent
ADAPTERS_DIR = adapters_dir()
CORE_DIR = core_dir()
TEMPLATES_DIR = templates_dir()
CONFIG_FILE = ".coding-os.yaml"
STATE_DIR = ".coding-os"
INSTALLED_MANIFEST = "installed-manifest.json"


def _cleanup_legacy_codex_instructions(project: Path) -> bool:
    """Remove obsolete .codex/instructions.md from older adapter versions.

    Pre-2026 Codex adapter concatenated src/core/rules + src/core/skills into
    .codex/instructions.md. Codex CLI never auto-loaded this file —
    AGENTS.md at the project root is the real SSOT. The stale file is
    removed on `cos update` so Codex doesn't get stale guidance via
    any agent-local tooling that happens to grep it.

    Returns True when a legacy file was deleted, False otherwise.
    """
    legacy = project / ".codex" / "instructions.md"
    if legacy.exists():
        legacy.unlink()
        return True
    return False


def _aggregate_world(agent: str, templates: tuple[str, ...], project: Path):
    """Build an AggregatedWorld for the given agent + stacks.

    Mirrors cli.main._build_world but re-implemented here to avoid importing
    from cli.main (which would create a circular import — main imports
    from update).
    """
    base = load_base_profile(TEMPLATES_DIR / "_base")
    stack_registry = load_stack_registry(TEMPLATES_DIR)
    adapter_registry = load_adapter_registry(ADAPTERS_DIR)
    if agent not in adapter_registry:
        raise click.ClickException(f"adapter '{agent}' not found in {ADAPTERS_DIR}")
    # Same relocation step as cli.main._build_world — `cos update` must not
    # regress a relocated project back to colliding src/backend globs.
    stacks = resolve_relocated_profiles(stack_registry, templates)
    return aggregate(base, stacks, adapter_registry[agent], project.name, today=today_iso())


# ---------------------------------------------------------------------------
# Data shapes
# ---------------------------------------------------------------------------


@dataclass
class AssetRef:
    """Logical asset: a name + where it should live under the agent root.

    `name` is the filename (hook/rule/command) or skill folder name.
    `rel_link` is the project-relative path where the symlink lives.
    `source_path` is the absolute path in CODING_OS_ROOT that it targets.
    """

    name: str
    rel_link: str
    source_path: Path


@dataclass
class ManifestDiff:
    added: dict[str, list[AssetRef]] = field(default_factory=dict)
    removed: dict[str, list[str]] = field(default_factory=dict)

    @property
    def has_changes(self) -> bool:
        return any(self.added.values()) or any(self.removed.values())


# ---------------------------------------------------------------------------
# Manifest builders
# ---------------------------------------------------------------------------


def _load_config(project: Path) -> dict:
    path = project / CONFIG_FILE
    if not path.exists():
        raise click.ClickException(f"Not a coding-os project ({CONFIG_FILE} missing in {project})")
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _load_adapter(agent: str):
    from cli.adapter_registry import load_adapter_registry

    adapters = load_adapter_registry(ADAPTERS_DIR)
    if agent not in adapters:
        raise click.ClickException(f"adapter '{agent}' not in registry")
    return adapters[agent]


def _build_target_assets(agent: str, templates: list[str]) -> dict[str, list[AssetRef]]:
    """Enumerate every symlink we expect to exist for this install."""
    adapter = _load_adapter(agent)
    result: dict[str, list[AssetRef]] = {
        "hooks": [],
        "skills": [],
        "rules": [],
        "commands": [],
    }

    # Hooks — always use src/core/hooks/ regardless of agent (path may differ).
    hooks_dir_rel = adapter.hooks_dir
    if hooks_dir_rel:
        for hook in sorted((CORE_DIR / "hooks").glob("*.sh")):
            result["hooks"].append(
                AssetRef(
                    name=hook.name,
                    rel_link=f"{hooks_dir_rel}/{hook.name}",
                    source_path=hook,
                )
            )

    # Rules — only when adapter supports them.
    rules_dir_rel = adapter.rules_dir
    if rules_dir_rel:
        for rule in sorted((CORE_DIR / "rules").glob("*.md")):
            result["rules"].append(
                AssetRef(
                    name=rule.name,
                    rel_link=f"{rules_dir_rel}/{rule.name}",
                    source_path=rule,
                )
            )

    # Core skills.
    skills_dir_rel = adapter.skills_dir
    if skills_dir_rel:
        for skill_dir in sorted((CORE_DIR / "skills").iterdir()):
            if not skill_dir.is_dir():
                continue
            skill_md = skill_dir / "SKILL.md"
            if not skill_md.exists():
                continue
            result["skills"].append(
                AssetRef(
                    name=skill_dir.name,
                    rel_link=f"{skills_dir_rel}/{skill_dir.name}/SKILL.md",
                    source_path=skill_md,
                )
            )
        # Stack skills.
        for stack in templates:
            stack_skills = TEMPLATES_DIR / stack / "skills"
            if not stack_skills.exists():
                continue
            for skill_dir in sorted(stack_skills.iterdir()):
                if not skill_dir.is_dir():
                    continue
                skill_md = skill_dir / "SKILL.md"
                if not skill_md.exists():
                    continue
                result["skills"].append(
                    AssetRef(
                        name=skill_dir.name,
                        rel_link=f"{skills_dir_rel}/{skill_dir.name}/SKILL.md",
                        source_path=skill_md,
                    )
                )

    # Commands — adapters that declare commands_dir in adapter.yaml.
    # Adapters merging commands into a single instructions file leave
    # commands_dir null and skip this branch.
    commands_dir_rel = getattr(adapter, "commands_dir", None)
    if commands_dir_rel:
        commands_src = CORE_DIR / "commands"
        if commands_src.exists():
            for cmd in sorted(commands_src.glob("*.md")):
                result["commands"].append(
                    AssetRef(
                        name=cmd.name,
                        rel_link=f"{commands_dir_rel}/{cmd.name}",
                        source_path=cmd,
                    )
                )
        # Role-agent slash commands installed by install-adapter.sh §8.
        # Each semantic agent (researcher.md, analyst.md, …) is exposed as
        # /role-<name>. README.md is excluded (catalog, not a role).
        agents_src = CORE_DIR / "thinking_os" / "agents"
        if agents_src.exists():
            for agent in sorted(agents_src.glob("*.md")):
                if agent.name == "README.md":
                    continue
                role = agent.stem
                result["commands"].append(
                    AssetRef(
                        name=f"role-{role}.md",
                        rel_link=f"{commands_dir_rel}/role-{role}.md",
                        source_path=agent,
                    )
                )

    return result


def _scan_project_assets(
    project: Path, categories: list[str], adapter_id: str
) -> dict[str, list[str]]:
    """Collect the set of asset names currently present in the project.

    Categories → directory mapping for the given adapter. Returns dict
    mapping category → list of on-disk asset names (paths relative to
    project root). Only looks at symlinks — copied files are user content.
    """
    adapter = _load_adapter(adapter_id)
    dir_by_cat = {
        "hooks": adapter.hooks_dir,
        "rules": adapter.rules_dir,
        "skills": adapter.skills_dir,
        "commands": getattr(adapter, "commands_dir", None),
    }

    present: dict[str, list[str]] = {}
    for cat in categories:
        base_rel = dir_by_cat.get(cat)
        if not base_rel:
            present[cat] = []
            continue
        base = project / base_rel
        if not base.exists():
            present[cat] = []
            continue
        names: list[str] = []
        if cat == "skills":
            for skill_dir in sorted(base.iterdir()):
                if skill_dir.is_dir() and (skill_dir / "SKILL.md").exists():
                    names.append(skill_dir.name)
        else:
            for entry in sorted(base.iterdir()):
                # Only track symlinks — copies are user-owned (e.g. path-scoped
                # stack rules like django-backend.md are regular files and
                # must not be flagged as orphans to remove).
                if entry.is_symlink():
                    names.append(entry.name)
        present[cat] = names
    return present


# ---------------------------------------------------------------------------
# Diff + apply
# ---------------------------------------------------------------------------


def _compute_diff(target: dict[str, list[AssetRef]], present: dict[str, list[str]]) -> ManifestDiff:
    diff = ManifestDiff()
    # For "skills", we compare skill_dir names; for others, file names.
    for cat, targets in target.items():
        current_names = set(present.get(cat, []))
        target_keys = {t.name if cat != "skills" else t.name: t for t in targets}
        # We need the skill-dir-name mapping: since rel_link for skill is
        # <dir>/<skill_name>/SKILL.md, the presence list stores <skill_name>.
        added = [t for key, t in target_keys.items() if key not in current_names]
        if added:
            diff.added[cat] = added
        removed = [n for n in current_names if n not in target_keys]
        if removed:
            diff.removed[cat] = removed
    return diff


def _apply_diff(project: Path, diff: ManifestDiff, adapter_id: str) -> None:
    """Create missing symlinks; remove orphans."""
    # Add
    for cat, items in diff.added.items():
        for item in items:
            link = project / item.rel_link
            link.parent.mkdir(parents=True, exist_ok=True)
            if link.is_symlink() or link.exists():
                link.unlink()
            link.symlink_to(item.source_path)
    # Remove orphans
    adapter = _load_adapter(adapter_id)
    dir_by_cat = {
        "hooks": adapter.hooks_dir,
        "rules": adapter.rules_dir,
        "skills": adapter.skills_dir,
        "commands": getattr(adapter, "commands_dir", None),
    }
    for cat, names in diff.removed.items():
        base_rel = dir_by_cat.get(cat)
        if not base_rel:
            continue
        base = project / base_rel
        for name in names:
            if cat == "skills":
                entry = base / name
                if entry.is_symlink():
                    # A symlinked skill dir is a community/extra link managed
                    # by `cos skill enable` — descending through it would
                    # delete the user's source files. Not update's to prune.
                    continue
                skill_md = entry / "SKILL.md"
                if skill_md.is_symlink() or skill_md.exists():
                    skill_md.unlink()
                try:
                    entry.rmdir()
                except OSError as exc:
                    logger.debug("orphan skill dir kept (non-empty): %s", exc)
            else:
                entry = base / name
                if entry.is_symlink() or entry.exists():
                    entry.unlink()


def _run_db_migrations(project: Path) -> bool:
    db = project / STATE_DIR / "coding-os.db"
    if not db.exists():
        return True
    import subprocess
    import sys

    brain = CORE_DIR / "thinking_os"
    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            f"import sys; sys.path.insert(0, {str(brain)!r}); "
            f"from database import init_db; init_db({str(db)!r})",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        click.echo(f"  WARN: DB migration failed (exit {proc.returncode})", err=True)
        if proc.stderr:
            click.echo(proc.stderr.strip(), err=True)
        return False
    return True


def _write_installed_manifest(
    project: Path,
    agent: str,
    templates: list[str],
    target: dict[str, list[AssetRef]],
) -> Path:
    manifest = {
        "coding_os_root": str(CODING_OS_ROOT),
        "installed_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "agent": agent,
        "templates": templates,
        "linked_assets": {cat: [a.name for a in items] for cat, items in target.items()},
    }
    state = project / STATE_DIR
    state.mkdir(parents=True, exist_ok=True)
    out = state / INSTALLED_MANIFEST
    out.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    stamp_core_version(state)
    return out


# ---------------------------------------------------------------------------
# Text formatting
# ---------------------------------------------------------------------------


def _format_diff(diff: ManifestDiff) -> str:
    if not diff.has_changes:
        return "No changes — already up to date."
    lines = []
    for cat in ("hooks", "rules", "skills", "commands"):
        add = diff.added.get(cat, [])
        rem = diff.removed.get(cat, [])
        if add:
            lines.append(f"  Added {cat}: {', '.join(a.name for a in add)}")
        if rem:
            lines.append(f"  Removed {cat}: {', '.join(rem)}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@click.command("update")
@click.option("--project-dir", "-d", default=".", help="Project directory")
@click.option("--dry-run", is_flag=True, default=False, help="Show diff without applying")
@click.option("--force", is_flag=True, default=False, help="Re-link all assets even if unchanged")
@click.option("--yes", "-y", is_flag=True, default=False, help="Skip confirmation")
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
def update(
    project_dir: str,
    dry_run: bool,
    force: bool,
    yes: bool,
    output_format: str,
) -> None:
    """Sync project assets with the current coding-os installation.

    Safe to re-run. Applies any new hooks/skills/rules/commands, removes
    orphans, and runs DB migrations. Never touches docs/, AGENTS.md, or
    user-authored files.
    """
    project = Path(project_dir).resolve()
    config = _load_config(project)
    agents = list(config.get("agents") or [])
    templates = list(config.get("templates") or [])

    if not agents:
        raise click.ClickException("no agents recorded in .coding-os.yaml")

    stamped_version = read_stamped_version(project / STATE_DIR)
    installed_version = current_core_version()
    if stamped_version and stamped_version != installed_version:
        click.echo(
            f"  WARN: core drift — project scaffolded by {stamped_version}, "
            f"installed core is {installed_version}; this update re-stamps it "
            "(release notes: docs/governance/release-process.md)",
            err=True,
        )

    overall_changes = False
    applied_summary: dict[str, dict] = {}

    for agent in agents:
        target = _build_target_assets(agent, templates)
        present = _scan_project_assets(
            project,
            list(target.keys()),
            agent,
        )
        diff = _compute_diff(target, present)

        if output_format == "text":
            click.echo(f"\n[{agent}] diff:")
            click.echo(_format_diff(diff))

        if diff.has_changes or force:
            overall_changes = True
            if not dry_run:
                _apply_diff(project, diff, agent)

        applied_summary[agent] = {
            "added": {k: [a.name for a in v] for k, v in diff.added.items()},
            "removed": {k: list(v) for k, v in diff.removed.items()},
        }

        if not dry_run:
            _write_installed_manifest(project, agent, templates, target)

    if not dry_run:
        # Remove legacy .codex/instructions.md (pre-2026 adapter wrote it,
        # Codex CLI never loaded it). AGENTS.md at project root is the SSOT.
        if _cleanup_legacy_codex_instructions(project):
            click.echo("  Removed legacy .codex/instructions.md (Codex reads AGENTS.md)")
            overall_changes = True

        # Module-registry migration (TASK-357): pre-module consumers gain an
        # explicit all-on state file. All-on ≡ the lazy default, so rendered
        # artifacts stay byte-identical — the file only makes the project's
        # module posture visible to the Config tab / cos module list.
        module_state_file = project / STATE_DIR / "subsystems-state.json"
        if not module_state_file.exists():
            module_state_file.parent.mkdir(parents=True, exist_ok=True)
            module_state_file.write_text(
                json.dumps({"version": 1, "disabled": []}, indent=2) + "\n", encoding="utf-8"
            )
            click.echo("  Migrated to module registry (all modules on)")

        # Aggregate the world once and reuse it for both the AGENTS.md backfill
        # and the Makefile materialization — `_aggregate_world` is the costly
        # step, so a single call serves both.
        if agents:
            try:
                world = _aggregate_world(agents[0], tuple(templates), project)
            except Exception as exc:
                world = None
                click.echo(f"  WARN: could not aggregate world ({exc})", err=True)
            if world is not None:
                # Fill the AGENTS.md gap for projects that predate the
                # render_agents_md path (pre-v0.2.0). The idempotent guard never
                # overwrites an existing file.
                if not (project / "AGENTS.md").exists() and ensure_agents_md(project, world):
                    click.echo("  Generated missing AGENTS.md")
                    overall_changes = True
                # Materialize / refresh stack-contributed make targets (TASK-392)
                # so the suites named in AGENTS.md stay runnable as stacks are
                # added/removed. User-authored Makefile targets are untouched.
                if materialize_makefile_targets(project, project / STATE_DIR, world):
                    click.echo("  Refreshed .coding-os/Makefile.stacks")
                    overall_changes = True

        # Symlinks still dangling AFTER re-link point at a source the current
        # registry no longer ships (or a meta-repo path that no longer exists)
        # — a re-install can never heal them, so prune (same contract as
        # sync-doctor; hub-architecture.md § Symlink health).
        leftover_dangling = [str(link) for link in _iter_symlinks(project) if _dangling(link)]
        if leftover_dangling:
            pruned_count = _prune_dangling(leftover_dangling)
            click.echo(
                f"  Pruned {pruned_count} dangling symlink(s) left by a moved/removed coding-os source"
            )
            overall_changes = True

        if not _run_db_migrations(project):
            click.echo("  ERROR: schema migration failed — DB may be inconsistent", err=True)
            click.echo(
                "  HINT: ensure coding-os deps are installed (`uv sync --extra rag` in the "
                "coding-os checkout), then re-run `cos update`",
                err=True,
            )
            raise SystemExit(1)

        # The hub imports core in-process and never hot-reloads; bounce a
        # running, now-stale hub so the fresh core is live (hub-architecture.md).
        try:
            from cli.hub_commands import _hub_code_is_stale, hub_restart

            stale, _ = _hub_code_is_stale()
            if stale:
                click.echo("  Restarting Hub to load updated core code…")
                click.get_current_context().invoke(hub_restart)
        except Exception as exc:
            logger.debug("hub auto-restart skipped: %s", exc)

    if output_format == "json":
        click.echo(
            json.dumps(
                {
                    "project": str(project),
                    "dry_run": dry_run,
                    "changes": overall_changes,
                    "per_agent": applied_summary,
                },
                indent=2,
            )
        )
    else:
        if dry_run:
            click.echo("\n(dry run — nothing applied)")
        elif overall_changes:
            click.echo("\nUpdate applied.")
        else:
            click.echo("Already up to date.")
