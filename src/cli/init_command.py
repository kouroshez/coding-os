"""`cos init` — compose the three layers into a consumer project."""

from __future__ import annotations

import contextlib
import json
import os
import sys
from pathlib import Path

import click

from cli._cli_paths import _refuse_coding_os_self_init
from cli._init_helpers import (
    InitError,
    ensure_gitignore,
    install_consumer_git_hooks,
    maybe_git_init,
    maybe_initial_commit,
    resolve_init_target,
)
from cli._init_phase import _run_scaffold_phase
from cli._init_preview import _dry_config_preview, _dry_run_preview
from cli._init_registries import (
    CONFIG_FILE,
    STATE_DIR,
    TEMPLATES_DIR,
    _apply_enable_modules,
    _enable_flag_help,
    _get_stack_registry,
    _module_flag_help,
    _profile_flag_help,
    _registered_slug,
    _validated_disabled_modules,
)
from cli._init_summary import print_completion_panel, print_git_result
from cli._init_world import (
    _detect_existing_install,
    _parse_agents,
    _prompt_agents,
    _prompt_name_and_location,
    _prompt_setup_mode,
    _prompt_templates,
    _sync_missing,
)


@click.command()
@click.option(
    "--agent",
    "-a",
    default=None,
    help="Agent adapter(s) to install, comma-separated (e.g. 'claude,codex'). Prompted if omitted (unless --yes).",
)
@click.option("--template", "-t", multiple=True, help="Stack template(s) to apply")
@click.option(
    "--preset",
    "preset_id",
    default=None,
    help="Named stack composition from templates/_presets/ (mutually exclusive with --template). Discover with `cos list-stacks`.",
)
@click.option(
    "--dry-config",
    is_flag=True,
    default=False,
    help="Print the merged .coding-os config preview (swimlane union + conflicts) for the requested stacks/preset and exit without writing anything.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Preview the would-be scaffold tree (files + composed configs) for the requested stacks/preset and exit without writing anything.",
)
@click.option(
    "--skills",
    "extra_skills_csv",
    default=None,
    help="Extra core skills beyond the stacks' own, comma-separated (wizard parity). Validated against the skill registry.",
)
@click.option(
    "--summary",
    "project_summary",
    default=None,
    help="1-2 paragraph project description; seeds docs/_meta/project-description.md (wizard parity, TASK-364 intake).",
)
@click.option(
    "--project-dir",
    "-d",
    default=None,
    help="Parent directory for the project (default: shell cwd). Mutually exclusive with --debug.",
)
@click.option(
    "--name",
    "-n",
    default=None,
    help="Create a new directory with this name inside --project-dir (or cwd). Validated: ^[a-z0-9][a-z0-9._-]{0,63}$",
)
@click.option(
    "--debug",
    is_flag=True,
    default=False,
    help="Scaffold into <coding-os>/.build/debug/<name>/ (or 'the-script-output'). Requires running inside the coding-os repo.",
)
@click.option(
    "--git/--no-git",
    default=True,
    help="Run `git init` in the new project (default: --git). Skipped silently if target is nested in an existing git repo.",
)
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Overwrite target directory if it already exists and is non-empty.",
)
@click.option(
    "--adopt",
    is_flag=True,
    default=False,
    help="Overlay onto an existing non-empty repo in place — never wipe user files (brownfield). Prefer `cos adopt`.",
)
@click.option(
    "--yes",
    "-y",
    is_flag=True,
    default=False,
    help="Non-interactive: use defaults for anything not passed via flags. Required in CI / non-TTY.",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Output format.",
)
@click.option(
    "--today",
    "today_override",
    default=None,
    help="ISO-8601 date to use for {{DATE}} substitutions (default: today). Deterministic fixture for golden tests.",
)
@click.option(
    "--no-register",
    is_flag=True,
    default=False,
    help="Skip writing this project to the global ~/.coding-os/registry.json. Used by sandbox fixtures (manifest-regen, golden tests) so disposable temp dirs don't pollute the hub registry.",
)
@click.option(
    "--index/--no-index",
    "do_index",
    default=True,
    help="Seed the doc-search index after scaffold (loads the embedding model, ~15s). --no-index skips it for fast / CI / fixture scaffolds — the index lives in the gitignored runtime DB, so golden captures never need it.",
)
@click.option(
    "--graph-index/--no-graph-index",
    "graph_index",
    default=False,
    help="Build the knowledge graph even under --no-index (AST walk, no embedding model). The Hub Composer passes this so a fast --no-index create still gets a populated Graph tab; default off keeps CI/fixture scaffolds (which pass --no-index) graph-free.",
)
@click.option(
    "--disable-module",
    "disable_module",
    multiple=True,
    help=_module_flag_help(),
)
@click.option(
    "--profile",
    "profile",
    default=None,
    help=_profile_flag_help(),
)
@click.option(
    "--enable-module",
    "enable_module",
    multiple=True,
    help=_enable_flag_help(),
)
def init(
    agent: str | None,
    template: tuple[str, ...],
    preset_id: str | None,
    dry_config: bool,
    dry_run: bool,
    extra_skills_csv: str | None,
    project_summary: str | None,
    project_dir: str | None,
    name: str | None,
    debug: bool,
    git: bool,
    force: bool,
    adopt: bool,
    yes: bool,
    output_format: str,
    today_override: str | None,
    no_register: bool,
    do_index: bool,
    graph_index: bool,
    disable_module: tuple[str, ...],
    profile: str | None,
    enable_module: tuple[str, ...],
) -> None:
    """Initialize coding-os in a project.

    Interactive by default — prompts for missing agent/template/name when a
    TTY is attached. Pass --yes for fully non-interactive runs (CI) using
    whatever flags are provided plus sensible defaults.
    """
    shell_cwd_raw = os.environ.get("PWD") or os.getcwd()
    shell_cwd = Path(shell_cwd_raw).resolve()

    # Runs BEFORE preset/profile resolution below, so a custom answer flows
    # through exactly the same validation as the flags. Skipped when the caller
    # already decided (flags, --yes, non-TTY).
    if not yes and sys.stdin.isatty() and preset_id is None and profile is None and not template:
        preset_id, profile = _prompt_setup_mode(preset_id=preset_id, profile=profile)

    # --preset expands to its stack list before anything else touches
    # `template` (config-composition.md § Presets).
    active_preset = None
    if preset_id:
        if template:
            click.echo("ERROR: --preset and --template are mutually exclusive.", err=True)
            sys.exit(2)
        from cli.preset_registry import load_preset_registry

        presets = load_preset_registry(
            TEMPLATES_DIR, known_stacks=set(_get_stack_registry().keys())
        )
        for warning in presets.warnings:
            click.echo(f"  WARN: {warning}", err=True)
        if preset_id not in presets:
            click.echo(
                f"ERROR: preset '{preset_id}' not found — available: "
                f"{sorted(presets.keys()) or '(none)'}",
                err=True,
            )
            sys.exit(2)
        active_preset = presets[preset_id]
        template = active_preset.stacks
        click.echo(f"Preset '{preset_id}' → stacks: {', '.join(template)}")

    # A --profile expands to a curated disabled-module set (subsystems.yaml::
    # profiles) MERGED with explicit --disable-module flags; omitted → the
    # registry default_profile. Resolved before validation so the union flows
    # through the same dependency-checked apply path (TASK-509).
    from cli.subsystems import load_profiles, resolve_profile

    _chosen_profile = profile or load_profiles()[1]
    try:
        _profile_disabled = resolve_profile(_chosen_profile)
    except ValueError as exc:
        click.echo(f"ERROR: {exc}", err=True)
        sys.exit(2)
    _explicit_disable = tuple(disable_module)
    disable_module = tuple(_profile_disabled) + tuple(disable_module)

    # Validate --disable-module BEFORE the dry-run/real split so the preview and
    # the real init reject the same ids (pass-3 review).
    disabled_modules = _validated_disabled_modules(disable_module)
    disabled_modules = _apply_enable_modules(disabled_modules, enable_module, _explicit_disable)

    if dry_config:
        _dry_config_preview(template, output_format)
        return

    if dry_run:
        _dry_run_preview(template, output_format, tuple(disabled_modules))
        return

    # --skills validated up-front (fail fast, wizard parity: the wizard only
    # offers known core skills).
    extra_skills: list[str] = []
    if extra_skills_csv:
        from cli.skill_registry import load_skill_registry
        from cli.skills_list import CORE_SKILLS_DIR

        known_skills = set(load_skill_registry(CORE_SKILLS_DIR).skills.keys())
        extra_skills = [s.strip() for s in extra_skills_csv.split(",") if s.strip()]
        unknown_skills = [s for s in extra_skills if s not in known_skills]
        if unknown_skills:
            click.echo(
                f"ERROR: unknown skill(s) {unknown_skills} — see `cos skills-list`.", err=True
            )
            sys.exit(2)

    # Idempotent detection: existing install → offer sync instead of re-init.
    existing = _detect_existing_install(shell_cwd) if not name and not project_dir else None
    if existing is not None:
        if output_format == "text":
            click.echo(
                f"Existing coding-os install detected at {shell_cwd}\n"
                f"  agents: {', '.join(existing['agents']) or '(none)'}\n"
                f"  templates: {', '.join(existing['templates']) or '(none)'}"
            )
        if yes or click.confirm("Sync missing components (links + config)?", default=True):
            _sync_missing(shell_cwd, output_format=output_format)
            return
        click.echo("Aborted.")
        sys.exit(0)

    # Non-TTY without --yes: refuse to guess the TARGET silently (TASK-359).
    # Gated on the target alone — a missing --agent is NOT pre-empted here,
    # because the agent prompt below already exits 2 when no input arrives,
    # while pre-empting would also reject a pipe that IS carrying the answer
    # (`printf 'claude\n0\ny\n' | cos init -d DIR`). The message still names
    # every missing flag so a bare `cos init` reports the whole gap at once.
    # Sits AFTER existing-install detection so the idempotent sync path keeps
    # working for a bare re-`cos init` inside a project.
    if not yes and not sys.stdin.isatty() and name is None and project_dir is None and not debug:
        missing = "--name and/or --project-dir"
        if agent is None:
            missing = f"--agent, {missing}"
        click.echo(
            f"ERROR: non-interactive shell — pass {missing} "
            "(or --yes to scaffold into the current directory).",
            err=True,
        )
        sys.exit(2)

    # Prompt for missing inputs. --yes disables all prompting. Prompts that
    # hit EOF (closed stdin — CI, scaffold tests) fall back to sensible
    # defaults instead of aborting, so flag-based test helpers that don't
    # provide stdin keep working.
    def _safe_prompt(prompt_fn, fallback):
        try:
            return prompt_fn()
        except (click.exceptions.Abort, click.exceptions.UsageError, EOFError):
            return fallback

    # Parse --agent: accepts comma-separated values (e.g. "claude,codex").
    agents: list[str] | None = None
    if agent is not None:
        agents = _parse_agents(agent)
    if agents is None:
        if yes:
            click.echo("ERROR: --agent is required with --yes.", err=True)
            sys.exit(2)
        agents = _safe_prompt(_prompt_agents, None)
        if agents is None:
            click.echo("ERROR: --agent is required (no input available).", err=True)
            sys.exit(2)
    if not template and not yes:
        template = _safe_prompt(_prompt_templates, ())
    if name is None and project_dir is None and not yes:
        name, project_dir = _safe_prompt(
            lambda: _prompt_name_and_location(shell_cwd),
            (None, None),
        )

    try:
        target = resolve_init_target(
            name=name,
            project_dir=project_dir,
            debug=debug,
            force=force,
            adopt=adopt,
            cwd=shell_cwd,
            # Refuse self-init BEFORE resolve_init_target's --force wipe runs.
            # Fires only when the target already exists and is non-empty.
            pre_wipe_hook=_refuse_coding_os_self_init,
        )
    except InitError as exc:
        click.echo(f"ERROR: {exc}", err=True)
        sys.exit(exc.exit_code)

    # Also check the (possibly fresh, possibly empty) target path — catches
    # the case where self-init was called without --force.
    _refuse_coding_os_self_init(target.path)

    project = target.path
    _refuse_coding_os_self_init(project)

    # JSON mode keeps stdout pure for programmatic callers, but the scaffold's
    # progress echoes are what the Hub's job runner scrapes for phase markers —
    # buffering them into the void left the create progress bar on "validate".
    # Streaming them to stderr keeps stdout clean AND the progress bar live.
    _stdout_redirect = (
        contextlib.redirect_stdout(sys.stderr)
        if output_format == "json"
        else contextlib.nullcontext()
    )

    if output_format == "text":
        click.echo(f"Initializing coding-os in {project}")
        click.echo(f"  Agents: {', '.join(agents)}")
        if template:
            click.echo(f"  Templates: {', '.join(template)}")
        if debug:
            click.echo("  Mode: debug (under .build/debug/)")
        if target.forced_empty:
            click.echo("  Note: target existed and was wiped (--force)")

    with _stdout_redirect:
        _run_scaffold_phase(
            agents,
            template,
            project,
            today=today_override,
            no_register=no_register,
            do_index=do_index,
            graph_index=graph_index,
            active_preset=active_preset,
            extra_skills=extra_skills,
            project_summary=project_summary,
            disabled_modules=disabled_modules,
        )

    git_result = maybe_git_init(target, enabled=git)
    # .gitignore whenever git is in play (fresh or nested repo) so the
    # mutating runtime DB never gets committed; the baseline commit runs
    # only when init created the repo — never sweep a parent project's tree.
    if git:
        ensure_gitignore(project)
    commit_result = maybe_initial_commit(target, enabled=git and git_result.ran)
    # Install the human-persona git hooks AFTER the baseline commit so that
    # tool-generated commit isn't gated by the freshly-installed pre-commit.
    hooks_result = install_consumer_git_hooks(project, enabled=git and git_result.ran)
    files_created = sum(1 for _ in project.rglob("*") if _.is_file())

    summary: dict[str, object] = {
        "status": "ok",
        "path": str(project),
        "slug": _registered_slug(project),
        "agents": agents,
        "templates": list(template),
        "debug": debug,
        "forced_empty": target.forced_empty,
        "git": {
            "ran": git_result.ran,
            "skipped_reason": git_result.skipped_reason,
            "error": git_result.error,
            "initial_commit": commit_result.committed,
            "commit_error": commit_result.error,
            "hooks_installed": list(hooks_result.installed),
            "hooks_error": hooks_result.error,
        },
        "files_created": files_created,
        "db_path": str(project / STATE_DIR / "coding-os.db"),
        "config_file": str(project / CONFIG_FILE),
        "warnings": (
            ["No stack template selected — AGENTS.md has placeholder routing. Run: cos add-stack"]
            if not template
            else []
        ),
    }

    if output_format == "json":
        click.echo(json.dumps(summary, indent=2))
        return

    # text mode — final summary
    print_git_result(git_result, commit_result, hooks_result)
    print_completion_panel(
        project,
        agents=agents,
        templates=tuple(template),
        files_created=files_created,
        disabled_modules=disabled_modules,
    )
