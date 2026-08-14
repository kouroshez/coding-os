"""Resolve the init "world" — config, prompts, and the aggregated stack view.

Owns everything that decides WHAT to build (name, location, stacks, adapter,
existing install) before _init_scaffold decides where the files land.
"""

from __future__ import annotations

from pathlib import Path

import click
import yaml

from cli._data_types import AggregatedWorld
from cli._init_registries import (
    ADAPTERS_DIR,
    CONFIG_FILE,
    STATE_DIR,
    TEMPLATES_DIR,
    VALID_AGENTS,
    _get_adapter_registry,
    _get_base_profile,
    _get_stack_registry,
)
from cli._init_scaffold import _link_stack_skills, _run_adapter_install
from cli.aggregator import aggregate, today_iso
from cli.stack_registry import resolve_relocated_profiles


def _build_world(
    agent: str,
    templates: tuple[str, ...],
    project: Path,
    *,
    today: str | None = None,
) -> AggregatedWorld:
    """Load base + requested stacks + adapter and aggregate into a world.

    `today` is an optional ISO-8601 override for deterministic fixtures
    (golden parity tests). Production callers leave it None so the
    current wall-clock date is used.
    """
    base = _get_base_profile()
    stack_registry = _get_stack_registry()
    adapter_registry = _get_adapter_registry()

    if agent not in adapter_registry:
        raise click.ClickException(f"adapter '{agent}' not found in {ADAPTERS_DIR}")
    adapter_profile = adapter_registry[agent]

    for t in templates:
        if t not in stack_registry:
            raise click.ClickException(
                f"stack '{t}' not found — available: {sorted(stack_registry.keys())}"
            )
    # Colliding structure.roots are relocated to src/services/<id> BEFORE
    # aggregation so every derived artifact is service-scoped
    # (project-anatomy.md § Glob/verify propagation).
    stack_profiles = resolve_relocated_profiles(stack_registry, templates)

    return aggregate(
        base,
        stack_profiles,
        adapter_profile,
        project.name,
        today=today or today_iso(),
    )


def _load_config(project_dir: Path) -> dict:
    """Load .coding-os.yaml from project directory."""
    config_path = project_dir / CONFIG_FILE
    if config_path.exists():
        with open(config_path) as f:
            return yaml.safe_load(f) or {}
    return {}


def _save_config(project_dir: Path, config: dict) -> None:
    """Save config to .coding-os.yaml."""
    config_path = project_dir / CONFIG_FILE
    with open(config_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)


def _detect_existing_install(path: Path) -> dict | None:
    """Return install snapshot dict if `path` has a coding-os config, else None.

    Used by `cos init` to pivot into idempotent sync mode when the user
    accidentally re-runs init in an already-initialized project.
    """
    cfg = path / CONFIG_FILE
    if not cfg.exists():
        return None
    try:
        data = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return None
    return {
        "agents": list(data.get("agents") or []),
        "templates": list(data.get("templates") or []),
        "version": data.get("version"),
        "state_dir": data.get("state_dir", STATE_DIR),
    }


def _sync_missing(project: Path, *, output_format: str = "text") -> None:
    """Re-link any missing adapter hooks/rules/commands/skills for a project.

    Non-destructive: existing files and symlinks are left alone; only gaps
    are filled. Used both by `cos init` on an already-initialized project
    and (in D.3) by `cos update`.
    """
    config = _load_config(project) or {}
    agents = config.get("agents") or []
    templates = tuple(config.get("templates") or [])
    added: list[str] = []

    for agent in agents:
        _run_adapter_install(agent, project)
        if templates:
            _link_stack_skills(agent, templates, project)
        added.append(agent)

    if output_format == "text":
        click.echo(f"  Synced adapters: {', '.join(added) if added else '(none)'}")
        click.echo("  (idempotent — existing files untouched)")


def _prompt_templates() -> tuple[str, ...]:
    """Ask the user which stack templates to apply. Returns a tuple of IDs.

    Stacks render grouped by language (template-authoring.md § Language
    layer): the user can answer with a stack id, a number, OR a bare
    language name — the latter resolves to that language's plain stack.
    """
    from cli.stack_registry import group_stacks_by_language, plain_stack_by_language

    registry = _get_stack_registry()
    if not registry.keys():
        return ()
    profiles = {sid: registry[sid] for sid in registry}
    groups = group_stacks_by_language(profiles)
    language_to_plain = plain_stack_by_language(profiles)

    available: list[str] = []
    click.echo("\nAvailable stacks (a bare language name picks its plain stack):")
    for language, members in groups.items():
        click.echo(f"  [{language}]")
        for profile in members:
            available.append(profile.id)
            click.echo(f"  {len(available)}. {profile.id:17s} — {profile.label}")
    click.echo("  0. none")
    click.echo("  (ready-made compositions: cos init --preset <id> — list with `cos list-stacks`)")
    raw = click.prompt(
        "Select stacks (numbers, names, or a language — e.g. '1,4', 'django,nextjs', 'go')",
        default="0",
        show_default=False,
    )
    tokens = [t.strip() for t in raw.split(",") if t.strip()]
    chosen: list[str] = []
    for tok in tokens:
        if tok == "0":
            return ()
        if tok.isdigit():
            i = int(tok) - 1
            if 0 <= i < len(available):
                chosen.append(available[i])
        elif tok in registry:
            chosen.append(tok)
        elif tok in language_to_plain:
            chosen.append(language_to_plain[tok])
    # Deduplicate while preserving order.
    seen = set()
    result: list[str] = []
    for s in chosen:
        if s not in seen:
            seen.add(s)
            result.append(s)
    return tuple(result)


def _prompt_setup_mode(
    *, preset_id: str | None, profile: str | None
) -> tuple[str | None, str | None]:
    """Offer recommended defaults or the full set of questions. Returns (preset, profile).

    Quick is the default and prints what it applied — an installer that silently
    decides for you gives no way to learn what is configurable. Custom asks the
    two questions the CLI previously accepted only as flags, so the terminal path
    reaches the same surface the Hub Composer already exposes.
    """
    from cli.subsystems import load_profiles

    try:
        return _ask_setup_mode(preset_id, profile, load_profiles())
    except (click.exceptions.Abort, click.exceptions.UsageError, EOFError) as exc:
        # An aborted prompt is a decision, not a failure: fall through to the
        # flags and registry defaults, but say so rather than looking hung.
        click.echo(f"  (setup questions skipped: {type(exc).__name__} — using defaults)", err=True)
        return preset_id, profile


def _ask_setup_mode(
    preset_id: str | None, profile: str | None, loaded_profiles: tuple[dict, str]
) -> tuple[str | None, str | None]:
    click.echo("\nSetup:")
    click.echo("  1. Quick   — recommended defaults, then pick your stacks  (recommended)")
    click.echo("  2. Custom  — also choose a ready-made preset and a module profile")
    choice = click.prompt("Select", default="1", show_default=True).strip()

    profiles, default_profile = loaded_profiles
    if choice != "2":
        click.echo("\nApplied recommended defaults:")
        click.echo(f"  Module profile:  {default_profile} (change later: cos module list)")
        click.echo("  Doc index:       on (embedding model loads once, ~15s)")
        click.echo("  Git:             init + baseline commit + human git hooks")
        click.echo("  Run `cos init --help` to set any of these explicitly.")
        return preset_id, profile

    return _prompt_preset(preset_id), _prompt_profile(profile, profiles, default_profile)


def _prompt_preset(preset_id: str | None) -> str | None:
    from cli.preset_registry import load_preset_registry

    presets = load_preset_registry(TEMPLATES_DIR, known_stacks=set(_get_stack_registry().keys()))
    names = sorted(presets.keys())
    if not names:
        return preset_id
    click.echo("\nReady-made stack compositions:")
    for index, name in enumerate(names, start=1):
        preset = presets[name]
        click.echo(f"  {index}. {name:18s} — {preset.label} ({', '.join(preset.stacks)})")
    click.echo("  0. none — pick individual stacks instead")
    raw = click.prompt("Select a preset", default="0", show_default=False).strip()
    if raw.isdigit():
        index = int(raw) - 1
        return names[index] if 0 <= index < len(names) else None
    return raw if raw in presets else None


def _prompt_profile(profile: str | None, profiles: dict, default_profile: str) -> str | None:
    names = sorted(profiles)
    if not names:
        return profile
    click.echo("\nModule profile — curates the MCP tool surface the agent sees:")
    for index, name in enumerate(names, start=1):
        disabled = profiles[name]
        detail = f"disables {', '.join(disabled)}" if disabled else "everything on"
        marker = "  (default)" if name == default_profile else ""
        click.echo(f"  {index}. {name:14s} — {detail}{marker}")
    raw = click.prompt("Select a profile", default=default_profile, show_default=True).strip()
    if raw.isdigit():
        index = int(raw) - 1
        return names[index] if 0 <= index < len(names) else default_profile
    return raw if raw in profiles else default_profile


def _parse_agents(raw: str) -> list[str]:
    """Parse and validate a comma-separated agent string (e.g. 'claude,codex').

    Raises click.ClickException if any token is not a known adapter.
    """
    tokens = [t.strip() for t in raw.split(",") if t.strip()]
    if not tokens:
        raise click.ClickException("--agent value is empty")
    invalid = [t for t in tokens if t not in VALID_AGENTS]
    if invalid:
        raise click.ClickException(
            f"unknown agent(s): {', '.join(invalid)} — available: {', '.join(VALID_AGENTS)}"
        )
    # Deduplicate preserving order.
    seen: set[str] = set()
    result: list[str] = []
    for t in tokens:
        if t not in seen:
            seen.add(t)
            result.append(t)
    return result


def _prompt_agents() -> list[str]:
    """Interactively prompt for one or more agents (comma-separated)."""
    label = ", ".join(VALID_AGENTS)
    raw = click.prompt(
        f"Agent(s) — comma-separated ({label})",
        default=VALID_AGENTS[0] if VALID_AGENTS else None,
    )
    return _parse_agents(raw)


def _prompt_name_and_location(shell_cwd: Path) -> tuple[str | None, str | None]:
    """Decide whether to use the current dir or create a subdir.

    Returns (name, project_dir) — either may be None to fall back to the
    resolver default. `project_dir` is returned as a string path to match
    the CLI option type.
    """
    default_name = shell_cwd.name
    use_current = click.confirm(
        f"Use current directory ({shell_cwd})?",
        default=True,
    )
    if use_current:
        return None, str(shell_cwd)
    name = click.prompt("Project name (subdirectory)", default=default_name)
    return name, str(shell_cwd)


def _derive_verify_from_world(world: AggregatedWorld) -> dict[str, str]:
    """Extract domain → command mapping from aggregated VERIFY_* substitutions.

    Looks for keys of the form `VERIFY_<DOMAIN>` (exact — not `_GLOB`, not
    `_SUITES`) and maps them to lowercased domain names. Strips surrounding
    backticks from values so `.coding-os.yaml.verify` stores raw shell
    commands, not display-formatted ones.
    """
    result: dict[str, str] = {}
    for key, value in world.substitutions.items():
        if not key.startswith("VERIFY_"):
            continue
        if key.endswith("_GLOB") or key.endswith("_SUITES"):
            continue
        domain = key.removeprefix("VERIFY_").lower()
        cleaned = value.strip().strip("`").strip()
        if not cleaned or cleaned == "(none)":
            continue
        result[domain] = cleaned
    return result
