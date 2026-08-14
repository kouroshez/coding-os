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

import json
import logging
from pathlib import Path

import click

logger = logging.getLogger(__name__)

from cli._init_helpers import (
    ensure_agents_md,
    ensure_entrypoint_symlink,
    materialize_ci_workflow,
    materialize_dockerfiles,
    materialize_makefile_targets,
)
from cli._resources import overlay_adapter_dirs, overlay_template_dirs
from cli._update_manifest import (
    ADAPTERS_DIR as ADAPTERS_DIR,
    CODING_OS_ROOT as CODING_OS_ROOT,
    CONFIG_FILE as CONFIG_FILE,
    CORE_DIR as CORE_DIR,
    INSTALLED_MANIFEST as INSTALLED_MANIFEST,
    STATE_DIR as STATE_DIR,
    TEMPLATES_DIR as TEMPLATES_DIR,
    AssetRef as AssetRef,
    ManifestDiff as ManifestDiff,
    _apply_diff as _apply_diff,
    _build_target_assets as _build_target_assets,
    _compute_diff as _compute_diff,
    _format_diff as _format_diff,
    _load_adapter as _load_adapter,
    _load_config as _load_config,
    _module_disabled_assets as _module_disabled_assets,
    _run_db_migrations as _run_db_migrations,
    _scan_project_assets as _scan_project_assets,
    _write_installed_manifest as _write_installed_manifest,
)
from cli.adapter_registry import load_adapter_registry
from cli.aggregator import aggregate, today_iso
from cli.core_version import (
    EDITABLE_UPGRADE_COMMAND,
    current_core_version,
    latest_published_version,
    read_stamped_version,
    upgrade_command,
)
from cli.stack_registry import (
    load_base_profile,
    load_stack_registry,
    resolve_relocated_profiles,
)
from cli.sync_all import _dangling, _iter_symlinks, _prune_dangling


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


def _sync_hook_registration(project: Path, agent: str, *, dry_run: bool) -> bool:
    """Re-register hooks in the agent's settings file from the shipped template.

    Linking a hook script is only half an install: the runtime fires what the
    settings file registers, so a newly shipped hook was symlinked by `cos
    update` and then never ran. Only the `hooks` key is replaced — the rest of
    the file (permissions, model, user edits) is the project's to own, which is
    why this does not just re-run install.sh.

    Returns True when the registration was out of date.
    """
    adapter = load_adapter_registry(ADAPTERS_DIR, overlay_dirs=overlay_adapter_dirs()).get(agent)
    if adapter is None or not adapter.supports_settings_json or not adapter.settings_file:
        return False
    template = ADAPTERS_DIR / agent / "settings.template.json"
    settings = project / adapter.settings_file
    if not template.is_file() or not settings.is_file():
        return False
    hooks_rel = f"{adapter.hooks_dir}" if adapter.hooks_dir else ""
    try:
        rendered = json.loads(
            template.read_text(encoding="utf-8").replace("{{HOOKS_DIR}}", hooks_rel)
        )
        current = json.loads(settings.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.debug("hook re-registration skipped for %s: %s", agent, exc)
        return False
    expected = rendered.get("hooks") or {}
    if current.get("hooks") == expected:
        return False
    if not dry_run:
        current["hooks"] = expected
        settings.write_text(json.dumps(current, indent=2) + "\n", encoding="utf-8")
    return True


def _release_notice(installed: str) -> str | None:
    """One line telling the user a newer coding-os exists and how to get it."""
    # `cos update` re-links assets from the package already on disk — it can
    # never change the installed version. Without this line the only signal a
    # consumer gets is a drift warning whose suggested fix silences it.
    latest = latest_published_version()
    if not latest or latest == installed or installed == "unknown":
        return None
    return (
        f"  A newer coding-os is published: {latest} (installed {installed}).\n"
        f"  Upgrade the package, then re-run this: {upgrade_command()}\n"
        f"  Installed from a checkout instead? {EDITABLE_UPGRADE_COMMAND}"
    )


def _aggregate_world(agent: str, templates: tuple[str, ...], project: Path):
    """Build an AggregatedWorld for the given agent + stacks.

    Mirrors cli.main._build_world but re-implemented here to avoid importing
    from cli.main (which would create a circular import — main imports
    from update).
    """
    base = load_base_profile(TEMPLATES_DIR / "_base")
    stack_registry = load_stack_registry(TEMPLATES_DIR, overlay_dirs=overlay_template_dirs())
    adapter_registry = load_adapter_registry(ADAPTERS_DIR, overlay_dirs=overlay_adapter_dirs())
    if agent not in adapter_registry:
        raise click.ClickException(f"adapter '{agent}' not found in {ADAPTERS_DIR}")
    # Same relocation step as cli.main._build_world — `cos update` must not
    # regress a relocated project back to colliding src/backend globs.
    stacks = resolve_relocated_profiles(stack_registry, templates)
    return aggregate(base, stacks, adapter_registry[agent], project.name, today=today_iso())


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

    if output_format == "text":
        notice = _release_notice(installed_version)
        if notice:
            click.echo(notice, err=True)

    overall_changes = False
    applied_summary: dict[str, dict] = {}

    for agent in agents:
        target = _build_target_assets(agent, templates, project)
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

        if _sync_hook_registration(project, agent, dry_run=dry_run):
            overall_changes = True
            if output_format == "text":
                click.echo(f"  Re-registered hooks in {agent} settings (was out of date)")

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

        # Module-registry migration: pre-module consumers gain an
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
                # Materialize / refresh stack-contributed make targets
                # so the suites named in AGENTS.md stay runnable as stacks are
                # added/removed. User-authored Makefile targets are untouched.
                if materialize_makefile_targets(project, project / STATE_DIR, world):
                    click.echo("  Refreshed .coding-os/Makefile.stacks")
                    overall_changes = True
                # Same delegation for the CI workflow — gated behind the cicd
                # module so a lean profile never grows a .github/ surface.
                from cli.subsystems import module_state

                if module_state(project).get("cicd", True):
                    if materialize_ci_workflow(project, world):
                        click.echo("  Refreshed .github/workflows/ci.yml")
                        overall_changes = True
                    if materialize_dockerfiles(project, world):
                        click.echo("  Refreshed backend Dockerfile(s)")
                        overall_changes = True

            # Backfill each agent's root entrypoint symlink — projects
            # scaffolded before adapter.yaml declared one never got it. Runs
            # after the AGENTS.md gap-fill above, which it links at.
            adapter_profiles = load_adapter_registry(
                ADAPTERS_DIR, overlay_dirs=overlay_adapter_dirs()
            )
            for agent in agents:
                profile = adapter_profiles.get(agent)
                entrypoint = profile.entrypoint_file if profile else None
                if ensure_entrypoint_symlink(project, entrypoint):
                    click.echo(f"  Linked {entrypoint} → AGENTS.md")
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
