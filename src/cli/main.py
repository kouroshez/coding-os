#!/usr/bin/env python3
"""
Coding OS — CLI tool for installing and managing the cognitive operating system.

Usage:
    coding-os init --agent claude,codex [--template django]
    coding-os add-adapter codex
    coding-os health
    coding-os adopt          # overlay onto an existing repo
    coding-os eject          # remove coding-os, keep your code/docs
"""

from __future__ import annotations

import contextlib
import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import click

from cli._init_boundaries import _aggregate_scaffold_boundaries  # noqa: F401
from cli._init_helpers import (
    InitError,
    ensure_agents_md,
    ensure_entrypoint_symlink,
    ensure_gitignore,
    install_consumer_git_hooks,
    maybe_git_init,
    maybe_initial_commit,
    resolve_init_target,
)
from cli._init_phase import (  # noqa: F401 — re-exported for tests + siblings
    _initial_doc_index,
    _initial_graph_index,
    _run_scaffold_phase,
)
from cli._init_preview import (  # noqa: F401 — re-exported for tests + siblings
    _dry_config_preview,
    _dry_run_preview,
    _scaffold_tree_preview,
)
from cli._init_registries import (  # noqa: F401 — re-exported for tests + siblings
    ADAPTERS_DIR,
    CONFIG_FILE,
    CORE_DIR,
    STATE_DIR,
    TEMPLATES_DIR,
    VALID_AGENTS,
    _apply_enable_modules,
    _discover_valid_agents,
    _discover_valid_templates,
    _enable_flag_help,
    _example_swimlane,
    _get_adapter_registry,
    _get_base_profile,
    _get_stack_registry,
    _module_flag_help,
    _profile_flag_help,
    _registered_slug,
    _reset_registries_for_tests,
    _subsystem_help_lists,
    _validated_disabled_modules,
)
from cli._init_scaffold import (  # noqa: F401 — re-exported for tests + siblings
    _apply_doc_conditions,
    _apply_template,
    _copy_workflow_docs,
    _link_stack_skills,
    _overlay_scaffold,
    _resolve_placeholders,
    _run_adapter_install,
    _service_relocations,
    module_scaffold_doc_rels,
)
from cli._init_world import (  # noqa: F401 — re-exported for tests + siblings
    _build_world,
    _derive_verify_from_world,
    _detect_existing_install,
    _load_config,
    _parse_agents,
    _prompt_agents,
    _prompt_name_and_location,
    _prompt_templates,
    _save_config,
    _sync_missing,
)
from cli._resources import (
    core_dir,
)
from cli.adapter_registry import load_adapter_registry
from cli.add_stack import add_stack as add_stack_cmd
from cli.brain_commands import (
    brain_decay as brain_decay_cmd,
    brain_gc as brain_gc_cmd,
    brain_sweep_changelog as brain_sweep_changelog_cmd,
    docs_index as docs_index_cmd,
    reindex as reindex_cmd,
    task_sync as task_sync_cmd,
)
from cli.doctor import doctor as doctor_cmd
from cli.list_adapters import list_adapters as list_adapters_cmd
from cli.list_stacks import list_stacks as list_stacks_cmd
from cli.materialize_file import materialize_file as materialize_file_cmd
from cli.remove_stack import remove_stack as remove_stack_cmd
from cli.setup import setup as setup_cmd
from cli.skills_list import skills_list as skills_list_cmd
from cli.tail_command import tail_cmd
from cli.update import update as update_cmd

# CODING_OS_ROOT is the source-checkout root — kept for dev-only operations; it
# is meaningless under a wheel install. The bundled DATA trees resolve via
# importlib so they are found under both src-layout and wheel installs (TASK-219).
CODING_OS_ROOT = Path(__file__).resolve().parent.parent.parent


VALID_TEMPLATES: list[str] = _discover_valid_templates()

# Stack and adapter metadata live in templates/*/stack.yaml and
# adapters/*/adapter.yaml. Adding a new stack or adapter is a pure data-file
# change — never touch this module.
#
# The caches below memoize registry loads within a single CLI invocation so
# cos init/doctor/add-stack don't re-parse YAML repeatedly. Tests can reset
# them via _reset_registries_for_tests().


# _merge_profiles, _build_substitutions, _list_installed_skills have all
# been replaced by the aggregator pipeline. See _build_world() above and
# src/cli/aggregator.py::aggregate() for the data-driven replacement.


# Tag-driven docs composition (TASK-360):
#  - file-level: a `module:<id>` token in the first-line header comment skips
#    the whole doc when that module is disabled;
#  - block-level: `<!-- if-stack:a,b -->` / `<!-- if-module:docs -->` ...
#    `<!-- end-if -->` keep the block only when ANY listed stack is installed /
#    the module is enabled. Markers and tags are stripped from the copy, so a
#    fully-default project's output is byte-identical to untagged sources.


def _bootstrap_hub_dir_if_first_run() -> None:
    """Seed ~/.coding-os/ the very first time the CLI is invoked."""
    import os as _os

    override = _os.environ.get("COS_REGISTRY_PATH")
    hub_dir = Path(override).parent if override else Path.home() / ".coding-os"
    try:
        if not hub_dir.exists():
            hub_dir.mkdir(parents=True, exist_ok=True)
        registry_file = hub_dir / "registry.json"
        if not registry_file.exists():
            # Same shape save_registry() writes — keep in sync with
            # cli.registry.Registry.to_dict().
            registry_file.write_text(
                '{\n  "version": 1,\n  "projects": []\n}\n',
                encoding="utf-8",
            )
    except OSError as exc:
        import logging as _logging

        _logging.getLogger("cli.main").debug("hub-dir bootstrap skipped: %s", exc)


from importlib.metadata import (
    PackageNotFoundError as _PackageNotFoundError,
    version as _pkg_version,
)


def _resolve_cli_version() -> str:
    try:
        return _pkg_version("coding-os")
    except _PackageNotFoundError:
        return "unknown"


def _warn_dangling_agent_links() -> None:
    """One stderr nudge when the cwd project's agent symlinks dangle (moved meta-repo).

    Fail-open by contract: the probe must never break or slow a command —
    hub-architecture.md § Symlink health is the spec for this passive layer.
    """
    try:
        project = Path.cwd()
        if not (project / CONFIG_FILE).exists():
            return
        from cli.sync_all import _dangling, _iter_symlinks

        for link in _iter_symlinks(project):
            if _dangling(link):
                click.echo(
                    "WARN: dangling coding-os symlinks detected (meta-repo moved or removed?) "
                    "— run: cos sync-doctor --repair",
                    err=True,
                )
                return
    except Exception as exc:
        import logging

        logging.getLogger(__name__).debug("dangling-link probe skipped: %s", exc)


@click.group()
@click.version_option(version=_resolve_cli_version(), prog_name="coding-os")
def cli() -> None:
    """Coding OS — the cognitive operating system that gives AI agents memory, structure, and discipline."""
    _warn_dangling_agent_links()
    # Route every stdlib logger.error from doctor /
    # health / any cos command into logging_os so the CLI process is no longer
    # blind to its own failures. Idempotent — install_bridge() removes a prior
    # bridge handler before adding. See docs/engineering/observability-eye.md §1.
    try:
        from core.logging_os import setup as _logging_os_setup

        _logging_os_setup(level="info")
    except Exception as _bridge_exc:  # pragma: no cover — never block the CLI on logging setup
        import logging as _logging

        _logging.getLogger("coding_os.cli").debug("logging_os bridge unavailable: %s", _bridge_exc)

    _bootstrap_hub_dir_if_first_run()


cli.add_command(doctor_cmd)
cli.add_command(list_stacks_cmd)
cli.add_command(list_adapters_cmd)
cli.add_command(add_stack_cmd)
cli.add_command(remove_stack_cmd)
cli.add_command(docs_index_cmd)
cli.add_command(task_sync_cmd)
cli.add_command(reindex_cmd)
cli.add_command(brain_decay_cmd)
cli.add_command(brain_gc_cmd)
cli.add_command(brain_sweep_changelog_cmd)
cli.add_command(update_cmd)
cli.add_command(setup_cmd)
cli.add_command(materialize_file_cmd)
cli.add_command(tail_cmd)
cli.add_command(skills_list_cmd)

from cli.module_commands import module_group as module_group_cmd
from cli.preset_commands import preset_group as preset_group_cmd
from cli.skill_commands import skill_group as skill_group_cmd
from cli.stack_lint import stack_lint as stack_lint_cmd
from cli.supervision_commands import supervision_group as supervision_group_cmd

cli.add_command(module_group_cmd)
cli.add_command(preset_group_cmd)
cli.add_command(skill_group_cmd)
cli.add_command(stack_lint_cmd)
cli.add_command(supervision_group_cmd)

# Durable error/log query CLI (cos errors / cos logs).
try:
    from cli.logs_commands import errors_cmd as _errors_cmd, logs_cmd as _logs_cmd

    cli.add_command(_logs_cmd)
    cli.add_command(_errors_cmd)
except ImportError as _logs_cli_exc:  # pragma: no cover — defensive
    import logging as _logging

    _logging.getLogger("coding_os.cli").debug("logs CLI unavailable: %s", _logs_cli_exc)

# Doc lifecycle CLI (cos doc-new / doc-history / doc-lint).
try:
    from cli.doc_commands import (
        doc_history_cmd as _doc_history_cmd,
        doc_lint_cmd as _doc_lint_cmd,
        doc_new_cmd as _doc_new_cmd,
    )

    cli.add_command(_doc_new_cmd)
    cli.add_command(_doc_history_cmd)
    cli.add_command(_doc_lint_cmd)
except ImportError as _doc_cli_exc:  # pragma: no cover — defensive
    import logging as _logging

    _logging.getLogger("coding_os.cli").debug("doc CLI unavailable: %s", _doc_cli_exc)

# Fast scope-aware verification: `cos verify --since-edit`.
try:
    from cli.verify_since_edit import verify_since_edit_cmd as _verify_cmd

    cli.add_command(_verify_cmd)
except ImportError as _verify_exc:  # pragma: no cover — defensive
    import logging as _logging

    _logging.getLogger("coding_os.cli").debug("verify CLI unavailable: %s", _verify_exc)

# Hub propagation: push meta-repo edits to every registered
# project via symlink re-link + DB migration.  Lives in src/cli/sync_all.py
# so registry.py stays focused on the JSON CRUD.
try:
    from cli.sync_all import sync_all_cmd, sync_doctor_cmd

    cli.add_command(sync_all_cmd)
    cli.add_command(sync_doctor_cmd)
except ImportError as _e:
    import logging as _logging

    _logging.getLogger("cli.main").debug("sync_all unavailable: %s", _e)

# board_os CLI surface (16 commands).
try:
    from cli.board_commands import BOARD_COMMANDS

    for _bc in BOARD_COMMANDS:
        cli.add_command(_bc)
except ImportError:
    pass  # board_os optional — don't break `cos` if deps missing.

# pr-mode multi-agent git executor (cos pr open/submit/status/cleanup/preflight).
try:
    from cli.pr_commands import pr_group as _pr_group

    cli.add_command(_pr_group)
except ImportError as _pr_cli_exc:  # pragma: no cover — defensive
    import logging as _logging

    _logging.getLogger("coding_os.cli").debug("pr CLI unavailable: %s", _pr_cli_exc)

# Scheduled jobs (CRON A/B).
try:
    from cli.cron_commands import cron_cmd

    cli.add_command(cron_cmd)
except ImportError as _e:
    import logging as _logging

    _logging.getLogger("cli.main").debug("cron CLI unavailable: %s", _e)

# cognition CLI (formula dispatches, persona selections, backtracks).
try:
    from cli.cognition import COGNITION_COMMANDS

    for _cc in COGNITION_COMMANDS:
        cli.add_command(_cc)
except ImportError:
    pass  # cognition optional — don't break `cos` if click missing.


def _resolve_project_dir(raw: str) -> Path:
    """Resolve the `--project-dir` value to an absolute path.

    Handles the `uv run --directory <coding-os>` invocation pattern
    correctly: when uv changes cwd to the coding-os repo before launching
    Python, a default `.` would resolve to coding-os itself, silently
    initializing the coding-os repo instead of the user's project.

    Resolution order:
      1. If the raw value is NOT exactly "." (user passed an explicit path)
         → resolve relative to the current Python cwd.
      2. Otherwise, prefer the shell's `$PWD` env var (uv and most shells
         preserve it — it's the original invocation directory).
      3. Fall back to `os.getcwd()` for non-uv invocations.

    This is defensive — `Path(".").resolve()` alone is dangerous under
    `uv --directory` because uv rewrites cwd before Python starts.
    """
    if raw != ".":
        return Path(raw).resolve()

    shell_pwd = os.environ.get("PWD")
    if shell_pwd and Path(shell_pwd).is_dir():
        return Path(shell_pwd).resolve()
    return Path.cwd().resolve()


def _refuse_coding_os_self_init(project: Path) -> None:
    """Block init from running inside the coding-os repo itself.

    The coding-os source tree already contains `AGENTS.md`, `Makefile`,
    `docs/`, `core/` etc — running `init` against it scatters scaffold
    files across the repo and can overwrite real development docs.
    Detect this by checking for the telltale `src/core/thinking_os/server.py`
    file and refuse.
    """
    from cli._init_helpers import is_coding_os_source_tree

    if is_coding_os_source_tree(project):
        click.echo(
            f"\nERROR: Refusing to init inside the coding-os repo itself ({project}).\n"
            f"  This path contains src/core/thinking_os/server.py — it is the source tree.\n"
            f"  Initializing here would scatter scaffold files into the repo.\n\n"
            f"  Fix:\n"
            f"    cd /path/to/your/actual-project\n"
            f"    uv run --directory {project} python -m cli.main init \\\n"
            f'      --agent claude --project-dir "$(pwd)"\n\n'
            f"  Or use the alias:\n"
            f"    alias cos-init='uv run --directory {project} python -m cli.main init'\n"
            f'    cos-init --agent claude --project-dir "$(pwd)"\n',
            err=True,
        )
        sys.exit(1)


@cli.command()
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
    if not yes and not sys.stdin.isatty():
        if name is None and project_dir is None and not debug:
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
    if git_result.ran:
        click.echo("  git: initialized")
        if commit_result.committed:
            click.echo("  git: baseline commit created")
        elif commit_result.error:
            click.echo(f"  git: WARN baseline commit failed — {commit_result.error}")
        if hooks_result.installed:
            click.echo(f"  git: hooks installed ({', '.join(hooks_result.installed)})")
        elif hooks_result.error:
            click.echo(f"  git: WARN hooks not installed — {hooks_result.error}")
    elif git_result.skipped_reason:
        click.echo(f"  git: skipped ({git_result.skipped_reason})")
    elif git_result.error:
        click.echo(f"  git: WARN {git_result.error}")

    click.echo("\ncoding-os initialized successfully!")
    click.echo(f"  Path:     {project}")
    click.echo(f"  Files:    {files_created}")
    click.echo(f"  Config:   {CONFIG_FILE}")
    click.echo(f"  State:    {STATE_DIR}/")
    click.echo("  Makefile: make help")
    click.echo("\nQuick start (no Hub required — this all runs from the CLI):")
    click.echo(f"  cd {project.name} && {agents[0] if agents else '<your agent>'}")
    if "tasks" in disabled_modules:
        click.echo("  cos module list        # Subsystems on here (the task board is off)")
    else:
        click.echo("  cos daily              # Project status + today's tasks")
        click.echo(
            f'  cos task-create --title "First task" --swimlane {_example_swimlane(project)} '
            '--kind chore --outcome "Walk the CLI loop end to end" --ready'
        )
        click.echo("  cos task-start <ID>    # Guide: docs/workflow/workflow-guide.md")

    if not template:
        available = sorted(_get_stack_registry().keys())
        click.echo(
            "\n  WARN: No stack template selected.\n"
            "  AGENTS.md has placeholder routing — agent works but lacks domain rules,\n"
            "  verify commands, and engineering guidelines.\n"
            f"  Add a stack now:  cos add-stack <id>\n"
            f"  Available stacks: {', '.join(available)}"
        )

    import platform as _platform

    if _platform.system() == "Darwin":
        click.echo("\nNightly maintenance (optional):")
        click.echo("  cos cron install  # launchd job — decay, learn, routing (daily 03:00)")


_STACK_MARKER_LANGUAGES: dict[str, str] = {
    # Build-manifest marker → base language. Resolved to that language's plain
    # stack via the registry below, so no stack id is ever hardcoded (Rule 11).
    "pyproject.toml": "python",
    "setup.py": "python",
    "requirements.txt": "python",
    "package.json": "typescript",
    "go.mod": "go",
    "Cargo.toml": "rust",
    "Gemfile": "ruby",
    "composer.json": "php",
    "pom.xml": "java",
    "build.gradle": "java",
}


def _detect_stacks_from_markers(path: Path) -> list[str]:
    """Resolve build-manifest markers in `path` to plain-stack ids via the
    registry — the brownfield-adopt stack proposal (no anatomy relocation)."""
    from cli.stack_registry import plain_stack_by_language

    registry = _get_stack_registry()
    profiles = {sid: registry[sid] for sid in registry}
    language_to_plain = plain_stack_by_language(profiles)
    detected: list[str] = []
    for marker, language in _STACK_MARKER_LANGUAGES.items():
        if not (path / marker).exists():
            continue
        stack = language_to_plain.get(language)
        if stack and stack not in detected:
            detected.append(stack)
    return detected


@cli.command()
@click.option(
    "--agent",
    "-a",
    default=None,
    help="Agent adapter(s) to install, comma-separated (required with --yes).",
)
@click.option(
    "--template",
    "-t",
    multiple=True,
    help="Stack template(s) to record — overrides build-marker auto-detection.",
)
@click.option(
    "--yes",
    "-y",
    is_flag=True,
    default=False,
    help="Non-interactive: adopt into the current directory using flags + defaults.",
)
@click.option("--git/--no-git", default=True, help="Run `git init` if the repo isn't already one.")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Output format.",
)
@click.option(
    "--no-register",
    is_flag=True,
    default=False,
    help="Skip writing this project to the global registry (sandbox fixtures).",
)
@click.option(
    "--index/--no-index",
    "do_index",
    default=True,
    help="Seed the doc-search index after adopt (--no-index for fast / CI runs).",
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
@click.pass_context
def adopt(
    ctx: click.Context,
    agent: str | None,
    template: tuple[str, ...],
    yes: bool,
    git: bool,
    output_format: str,
    no_register: bool,
    do_index: bool,
    disable_module: tuple[str, ...],
    profile: str | None,
    enable_module: tuple[str, ...],
) -> None:
    """Overlay coding-os onto an existing repo without touching user code.

    Adds .coding-os/ state, adapter dirs and AGENTS.md in place, auto-detecting
    stacks from build markers (pyproject.toml / package.json / go.mod / …). An
    already-adopted repo pivots to the idempotent sync path instead of re-installing.
    """
    target = Path(os.environ.get("PWD") or os.getcwd()).resolve()

    # Already adopted → idempotent sync (same path as a bare re-`cos init`).
    if _detect_existing_install(target) is not None:
        if output_format == "text":
            click.echo(f"coding-os already present at {target} — syncing missing components.")
        _sync_missing(target, output_format=output_format)
        return

    # Propose stacks from build markers unless the caller pinned --template.
    if not template:
        detected = _detect_stacks_from_markers(target)
        if detected and output_format == "text":
            click.echo(f"Detected stacks: {', '.join(detected)}")
        template = tuple(detected)

    # Reuse the init scaffold in place — name/project_dir unset ⇒ current dir,
    # force unset ⇒ no wipe, so pre-existing user files are never overwritten.
    ctx.invoke(
        init,
        agent=agent,
        template=template,
        adopt=True,
        yes=yes,
        git=git,
        output_format=output_format,
        no_register=no_register,
        do_index=do_index,
        disable_module=disable_module,
        profile=profile,
        enable_module=enable_module,
    )


@cli.command("add-adapter")
@click.argument("agent", type=click.Choice(VALID_AGENTS))
@click.option("--project-dir", "-d", default=".", help="Project directory")
def add_adapter(agent: str, project_dir: str) -> None:
    """Add an additional agent adapter to the project."""
    project = _resolve_project_dir(project_dir)
    config = _load_config(project)

    if not config:
        click.echo("ERROR: No .coding-os.yaml found. Run 'coding-os init' first.", err=True)
        sys.exit(1)

    agents = config.get("agents", [])
    if agent in agents:
        click.echo(f"Adapter '{agent}' is already installed.")
        return

    click.echo(f"Adding {agent} adapter...")
    _run_adapter_install(agent, project)

    agents.append(agent)
    config["agents"] = agents
    _save_config(project, config)
    click.echo(f"  Updated {CONFIG_FILE}")

    # AGENTS.md is the canonical per-project instruction file (read by both
    # Claude and Codex). `cos init` generates it, but older projects or
    # partial installs may be missing it — fill the gap so the newly added
    # adapter has something to read on first session.
    templates = tuple(config.get("templates", []) or [])
    world = _build_world(agent, templates, project)
    if ensure_agents_md(project, world):
        click.echo("  Generated AGENTS.md")

    entrypoint = _get_adapter_registry()[agent].entrypoint_file
    if ensure_entrypoint_symlink(project, entrypoint):
        click.echo(f"  Linked {entrypoint} → AGENTS.md")


@cli.command("codex-mcp-install")
@click.option(
    "--config",
    "config_path",
    default=None,
    help="Codex config file (default: ./.codex/config.toml)",
)
@click.option(
    "--global",
    "global_scope",
    is_flag=True,
    default=False,
    help="Write to ~/.codex/config.toml instead of the project-local .codex/config.toml",
)
@click.option("--dry-run", is_flag=True, default=False, help="Print the snippet without writing")
def codex_mcp_install(config_path: str | None, global_scope: bool, dry_run: bool) -> None:
    """Register the coding-os MCP server in Codex config.

    Codex CLI supports both user-level ~/.codex/config.toml and trusted
    project overrides in .codex/config.toml. This command defaults to the
    project-local config so coding-os MCP stays scoped to the current repo;
    pass `--global` only when you explicitly want the server available
    everywhere. Safe to re-run — it repairs or replaces the
    `[mcp_servers.coding-os]` section idempotently.

    Uses append-based text edits (no TOML parser required) so it works on
    Python 3.10 and preserves any hand-authored comments in config.toml.
    """
    if config_path and global_scope:
        raise click.ClickException("use either --config or --global, not both")

    default_path = (
        Path.home() / ".codex" / "config.toml"
        if global_scope
        else Path.cwd() / ".codex" / "config.toml"
    )
    target = Path(config_path).expanduser().resolve() if config_path else default_path

    has_cos = shutil.which("cos") is not None
    if has_cos:
        snippet = '\n[mcp_servers.coding-os]\ncommand = "cos"\nargs = ["server-start"]\n'
        command = "cos"
        args = ["server-start"]
    else:
        server_py = core_dir("thinking_os", "server.py").as_posix()
        python = sys.executable
        snippet = f'\n[mcp_servers.coding-os]\ncommand = "{python}"\nargs = ["{server_py}"]\n'
        command = python
        args = [server_py]

    if dry_run:
        click.echo(f"# Would append to {target}:")
        click.echo(snippet.rstrip())
        return

    # Locate the adapter that ships an MCP-helper script. This is the
    # codex adapter by design — discovered via registry metadata so the
    # adapter id is not hardcoded in Python code (tests/test_no_hardcoded_stacks).
    _helper_profile = next(
        (p for p in load_adapter_registry(ADAPTERS_DIR).values() if p.mcp_helper),
        None,
    )
    if _helper_profile is None:
        raise click.ClickException(
            "no adapter declares mcp_helper in adapter.yaml; cannot install MCP"
        )
    helper = _helper_profile.source_dir / _helper_profile.mcp_helper
    proc = subprocess.run(
        [sys.executable, str(helper), str(target), command, *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise click.ClickException(
            proc.stderr.strip() or f"failed to configure coding-os MCP in {target}"
        )

    status = (proc.stdout or "").strip()
    if status.startswith("already configured"):
        click.echo(f"Already registered in {target} — no changes made.")
        return

    click.echo(f"OK: registered coding-os MCP in {target}")
    click.echo("Reload Codex CLI (or start a new session) to pick up the new server.")


@cli.command()
@click.option("--project-dir", "-d", default=".", help="Project directory")
def health(project_dir: str) -> None:
    """Check coding-os health status."""
    project = _resolve_project_dir(project_dir)
    config = _load_config(project)

    click.echo("Coding OS Health Check")
    click.echo("=" * 40)

    # Config
    if config:
        click.echo(f"  Config:     OK ({CONFIG_FILE})")
        click.echo(f"  Agents:     {', '.join(config.get('agents', []))}")
        click.echo(f"  Templates:  {', '.join(config.get('templates', [])) or 'none'}")
    else:
        click.echo("  Config:     MISSING (run 'coding-os init')")
        return

    # State dir
    state = project / config.get("state_dir", STATE_DIR)
    if state.exists():
        click.echo(f"  State dir:  OK ({state.name}/)")
    else:
        click.echo("  State dir:  MISSING")

    # Database
    db_path = state / "coding-os.db"
    if db_path.exists():
        size_kb = db_path.stat().st_size / 1024
        click.echo(f"  Database:   OK ({size_kb:.0f} KB)")
    else:
        click.echo("  Database:   MISSING")

    # Hooks
    hooks_dir = CORE_DIR / "hooks"
    hook_count = len(list(hooks_dir.glob("*.sh"))) if hooks_dir.exists() else 0
    click.echo(f"  Core hooks: {hook_count} scripts")

    # MCP server
    server_py = CORE_DIR / "thinking_os" / "server.py"
    if server_py.exists():
        click.echo("  MCP server: OK")
    else:
        click.echo("  MCP server: MISSING")

    click.echo("")
    click.echo("Run 'coding-os init' to fix any missing components.")


@cli.command()
@click.option("--project-dir", "-d", default=".", help="Project directory")
def materialize(project_dir: str) -> None:
    """Convert coding-os symlinks to real files (self-contained project)."""
    project = _resolve_project_dir(project_dir)
    materialized = 0

    for root, _dirs, files in os.walk(project):
        for name in files:
            filepath = Path(root) / name
            if filepath.is_symlink():
                target = filepath.resolve()
                if target.exists():
                    filepath.unlink()
                    shutil.copy2(target, filepath)
                    materialized += 1
                    if materialized % 50 == 0:
                        click.echo(f"  … materialized {materialized} symlinks so far", err=True)

    click.echo(f"Materialized {materialized} symlinks to real files.")
    click.echo("Project is now self-contained.")


def _is_coding_os_symlink(link: Path) -> bool:
    """True if `link` is coding-os wiring — dangling or resolving into the
    meta-repo checkout (a user's own symlink elsewhere is left alone)."""
    try:
        real = link.resolve()
    except OSError:
        return True  # broken/cyclic — it was one of ours
    if not real.exists():
        return True  # dangling: source moved/removed
    try:
        real.relative_to(CODING_OS_ROOT.resolve())
        return True
    except ValueError:
        return False


@cli.command()
@click.option("--project-dir", "-d", default=".", help="Project directory")
@click.option("--yes", "-y", is_flag=True, default=False, help="Skip the confirmation prompt.")
def eject(project_dir: str, yes: bool) -> None:
    """Remove coding-os from a project, keeping your code and docs.

    Deletes coding-os symlinks, the .coding-os/ state dir and the generated
    AGENTS.md / .coding-os.yaml entrypoints, then deregisters the project. Real
    files you authored (source, docs, anything that isn't a managed symlink) are
    never touched. Re-running on an already-ejected project is a no-op.
    """
    project = _resolve_project_dir(project_dir)
    state_dir = project / STATE_DIR
    config = project / CONFIG_FILE
    coding_os_links = [
        p
        for p in (Path(root) / n for root, _d, fs in os.walk(project) for n in fs)
        if p.is_symlink() and _is_coding_os_symlink(p)
    ]
    # An adapter's root entrypoint is a generated symlink to AGENTS.md; it
    # points at a sibling, so the meta-repo filter above misses it. Only a
    # still-symlinked one is ours — a user who replaced it with a real file
    # keeps that file. Filenames come from adapter.yaml, never a literal here.
    generated_entrypoints = [config, project / "AGENTS.md"]
    generated_entrypoints += [
        link
        for name in sorted(
            {p.entrypoint_file for p in _get_adapter_registry().values() if p.entrypoint_file}
        )
        if (link := project / name).is_symlink()
    ]

    present = [f for f in generated_entrypoints if f.exists() or f.is_symlink()]
    if not coding_os_links and not state_dir.exists() and not present:
        click.echo("No coding-os install found here — nothing to eject.")
        return

    if not yes and not click.confirm(
        f"Remove coding-os from {project}? Your code and docs stay.", default=False
    ):
        click.echo("Aborted.")
        return

    for link in coding_os_links:
        link.unlink()
    removed_files = 0
    for f in present:
        f.unlink()
        removed_files += 1
    removed_state = False
    if state_dir.exists():
        shutil.rmtree(state_dir)
        removed_state = True

    # Prune adapter dirs left empty after the symlinks went; keep any that still
    # hold real (user-authored or materialized) files.
    kept_dirs: list[str] = []
    for agent_dir in sorted({p.parent for p in coding_os_links if p.parent.name.startswith(".")}):
        if agent_dir.is_dir() and not any(agent_dir.iterdir()):
            agent_dir.rmdir()
        elif agent_dir.is_dir():
            kept_dirs.append(agent_dir.name)

    from cli.registry import remove_project

    deregistered = False
    try:
        deregistered = remove_project(str(project)) is not None
    except Exception as exc:  # registry is best-effort — never block an eject
        _logging.getLogger("coding_os.cli").debug("eject: deregister skipped: %s", exc)

    click.echo(f"Ejected coding-os from {project}")
    click.echo(
        f"  removed: {len(coding_os_links)} symlinks · {removed_files} config file(s)"
        + (" · .coding-os/ state" if removed_state else "")
        + (" · global-registry entry" if deregistered else "")
    )
    kept = "your source, docs, and any files you authored"
    if kept_dirs:
        kept += f" (incl. real files under {', '.join(sorted(set(kept_dirs)))})"
    click.echo(f"  kept:    {kept}")


@cli.command("hooks-dir")
def hooks_dir() -> None:
    """Print the path to the core hooks directory."""
    click.echo(CORE_DIR / "hooks")


@cli.command("hooks-log")
@click.option("--project-dir", "-d", default=".", help="Project directory")
@click.option("-n", "tail_count", default=50, help="Show last N lines (default 50)")
@click.option("--follow", "-f", is_flag=True, default=False, help="Follow new entries (tail -f)")
@click.option("--agent", type=str, default=None, help="Filter by agent (claude|codex|unknown)")
@click.option("--session", type=str, default=None, help="Filter by session id (substring match)")
@click.option("--task", type=str, default=None, help="Filter by task name (substring match)")
@click.option("--hook", type=str, default=None, help="Filter by hook name (substring match)")
@click.option(
    "--all",
    "--verbose",
    "show_all",
    is_flag=True,
    default=False,
    help="Show lifecycle rows (enter/ok) too; default hides them.",
)
def hooks_log(
    project_dir: str,
    tail_count: int,
    follow: bool,
    agent: str | None,
    session: str | None,
    task: str | None,
    hook: str | None,
    show_all: bool,
) -> None:
    """Show recent hook activity from .coding-os/.hooks.log.

    Hooks call `cos_log_hook` (from src/core/hooks/cos-env.sh) on fire / block /
    allow / warn. Every line carries `agent=X session=Y task=Z` identity
    fields so you can filter by any combination:

        cos hooks-log --agent claude                   # only claude runs
        cos hooks-log --session ses-20260418-143638-c769
        cos hooks-log --task governance-mcp-envelope --hook enforce-
        cos hooks-log --agent codex --follow           # live codex stream
        cos hooks-log --all                            # include enter/ok noise

    By default only decision-states (fire/block/warn/paths/reminded/full/
    debounced/skip/bypass) are shown; lifecycle rows ([enter]/[ok]) are hidden
    behind --all/--verbose. Filters are AND-ed together (case-sensitive
    substring match).
    """
    project = _resolve_project_dir(project_dir)
    config = _load_config(project) or {}
    state = project / config.get("state_dir", STATE_DIR)
    log_path = state / ".hooks.log"

    if not log_path.exists():
        click.echo(f"No hook activity yet ({log_path} does not exist).")
        click.echo(
            "Hint: hooks log on fire — if you expected events, check"
            " .claude/settings.json or .codex/hooks.json wiring."
        )
        return

    # Lifecycle actions are bookkeeping, not decisions — hide them by default
    # so `cos hooks-log` surfaces signal (fire/block/warn/...) over noise.
    lifecycle_actions = {"[enter]", "[ok]"}

    def _is_decision_state(line: str) -> bool:
        return not any(token in line for token in lifecycle_actions)

    filters: list[str] = []
    if agent:
        filters.append(f"agent={agent}")
    if session:
        filters.append(f"session={session}")
    if task:
        filters.append(f"task={task}")
    if hook:
        filters.append(f"[{hook}")

    if follow:
        tail_cmd = f"tail -f -n {tail_count} {shlex.quote(str(log_path))}"
        pipe = [tail_cmd]
        if not show_all:
            pipe.append("grep --line-buffered -vE '\\[(enter|ok)\\]'")
        pipe.extend(f"grep -F --line-buffered {shlex.quote(f)}" for f in filters)
        subprocess.run(["bash", "-c", " | ".join(pipe)])
        return

    try:
        lines = log_path.read_text(errors="replace").splitlines()
    except OSError as exc:
        click.echo(f"Could not read {log_path}: {exc}", err=True)
        return
    matched = [
        ln for ln in lines if all(f in ln for f in filters) and (show_all or _is_decision_state(ln))
    ]
    for ln in matched[-tail_count:]:
        click.echo(ln)


@cli.command("hooks-list")
@click.option("--agent", type=str, default=None, help="Filter by adapter (claude|codex)")
@click.option("--category", type=str, default=None, help="Filter by category")
@click.option("--phase", type=str, default=None, help="Filter by phase")
def hooks_list(agent: str | None, category: str | None, phase: str | None) -> None:
    """List hooks registered in src/core/hooks/registry.yaml with filters.

    Reads the manifest SSOT and prints a summary. With --agent, filters to
    hooks whose events fit that adapter's declared capabilities — answers
    "what enforcement is active for Codex?" without grepping settings.
    """
    from cli.hook_renderer import list_hooks_for_agent, load_registry

    registry_path = CORE_DIR / "hooks" / "registry.yaml"
    if not registry_path.exists():
        click.echo(f"ERROR: {registry_path} not found", err=True)
        sys.exit(1)

    entries = load_registry(registry_path)
    if agent:
        entries = list_hooks_for_agent(entries, agent, ADAPTERS_DIR)
    if category:
        entries = [h for h in entries if h.category == category]
    if phase:
        entries = [h for h in entries if str(h.phase) == phase]

    if not entries:
        click.echo("No hooks match the filters.")
        return

    by_cat: dict[str, list] = {}
    for h in entries:
        by_cat.setdefault(h.category or "uncategorized", []).append(h)

    for cat in sorted(by_cat):
        click.echo(f"\n[{cat}]")
        for h in by_cat[cat]:
            events = ", ".join(
                f"{e['event']}::{e.get('matcher', '')}".rstrip(":") for e in h.events
            )
            click.echo(f"  {h.id:30s}  phase={h.phase!s:3s}  events=[{events}]")
            if h.description:
                click.echo(f"    {h.description}")
    click.echo("")


@cli.command("server-start")
def server_start() -> None:
    """Start the thinking_os MCP server (wrapper used by .mcp.json).

    Projects register `cos server-start` in their .mcp.json so the MCP
    entry stays portable — coding-os location is resolved at call time by
    whichever `cos` binary is on PATH, not hardcoded per-install.

    Historically this wrapper re-entered `uv run --directory ...`, which
    dragged in `~/.cache/uv` at every MCP launch. In sandboxed runtimes
    that cache path may be unreadable, causing MCP startup to fail before
    the server process even booted. We already have a Python interpreter
    available — the one running `cos` itself — so execute `server.py`
    directly with that interpreter instead.

    We still capture the caller's cwd (the real project root the agent
    launched us from) and export it as COS_DB_PATH / COS_STATE_DIR so the
    server reads the right DB regardless of its own source location.
    """
    server_py = CORE_DIR / "thinking_os" / "server.py"
    if not server_py.exists():
        click.echo(f"ERROR: MCP server not found at {server_py}", err=True)
        sys.exit(1)

    caller_cwd = Path.cwd().resolve()
    env = os.environ.copy()
    # Only inject if the caller hasn't already set them — respects
    # explicit overrides for tests / multi-project setups.
    env.setdefault(
        "COS_DB_PATH",
        str(caller_cwd / STATE_DIR / "coding-os.db"),
    )
    env.setdefault(
        "COS_STATE_DIR",
        str(caller_cwd / STATE_DIR),
    )

    # Exec so signals / stdio pass through cleanly (MCP is stdio-based).
    python = sys.executable
    os.execvpe(
        python,
        [
            python,
            str(server_py),
        ],
        env,
    )


@cli.command("session-state")
@click.option("--project-dir", "-d", default=".", help="Project directory")
def session_state(project_dir: str) -> None:
    """Show current session gate, task, and skill state."""
    import time

    from cli.board_commands import _detect_agent_runtime

    project = Path(project_dir).resolve()
    agent = os.environ.get("COS_AGENT") or _detect_agent_runtime()
    if not agent:
        adapters = sorted(load_adapter_registry(ADAPTERS_DIR).keys())
        if not adapters:
            click.echo("No adapters registered under src/adapters/.", err=True)
            sys.exit(1)
        agent = adapters[0]
    agent_dir = project / ".coding-os" / agent

    if not agent_dir.exists():
        click.echo(f"No session state at {agent_dir}")
        sys.exit(1)

    session_file = agent_dir / "session-id"
    current_session = session_file.read_text().strip() if session_file.exists() else ""

    def _read_state(path: Path, max_age: int = 7200) -> tuple[str, str]:
        if not path.exists():
            return ("none", "")
        try:
            content = path.read_text().splitlines()[0] if path.exists() else ""
        except OSError:
            return ("error", "")
        parts = content.split(" ", 1)
        file_session = parts[0] if parts else ""
        value = parts[1] if len(parts) > 1 else ""
        if current_session and file_session and file_session != current_session:
            return ("session-mismatch", value)
        age = int(time.time() - path.stat().st_mtime)
        if age > max_age:
            return (f"stale ({age // 60}min old, max {max_age // 60}min)", value)
        return ("valid", value)

    gate_status, gate_val = _read_state(agent_dir / ".thinking_os-gate")
    task_status, task_val = _read_state(agent_dir / ".task-current")
    skill_status, skill_val = _read_state(agent_dir / ".active-skill")
    zoom_status, _ = _read_state(agent_dir / ".zoom-checkpoint")
    doc_status, _ = _read_state(agent_dir / ".doc-anchor")

    click.echo(f"Session   : {current_session or '(unset)'}")
    click.echo(f"Agent     : {agent}")
    click.echo(f"Gate      : {gate_status:30s} {gate_val}")
    click.echo(f"Zoom      : {zoom_status}")
    click.echo(f"Task      : {task_status:30s} {task_val}")
    click.echo(f"Skill     : {skill_status:30s} {skill_val}")
    click.echo(f"DocAnchor : {doc_status}")

    if "stale" in gate_status or gate_status == "none":
        click.echo("")
        click.echo("Gate not valid — next Write/Edit on .py/.ts/.tsx will BLOCK")
        click.echo(f'   Re-record: bash "{agent_dir}/hooks/write-state.sh" \\')
        click.echo('              .thinking_os-gate "CLEAR 1"')
        click.echo("   (bare basename auto-routes to $COS_PANEL_DIR via cos_state_path)")


# ---------------------------------------------------------------------------
# graph_os subcommand family (`cos graph-*`).
# Registration lives in src/cli/graph_commands.py so the main file stays lean.
# ---------------------------------------------------------------------------
try:
    from cli import graph_commands as _graph_commands

    _graph_commands.register(cli)
except ImportError as _graph_cli_exc:  # pragma: no cover — defensive
    import logging as _logging

    _logging.getLogger("coding_os.cli").debug("graph_os CLI unavailable: %s", _graph_cli_exc)


# ---------------------------------------------------------------------------
# DB lifecycle — `cos db-stats`, `cos db-reset`. Spec: docs/playbooks/db-reset.md.
# ---------------------------------------------------------------------------
try:
    from cli import db_reset as _db_reset

    _db_reset.register(cli)
except ImportError as _db_reset_exc:  # pragma: no cover — defensive
    import logging as _logging

    _logging.getLogger("coding_os.cli").debug("db_reset CLI unavailable: %s", _db_reset_exc)


# ---------------------------------------------------------------------------
# S4/S5 — registry + hub CLI. (`cos web` removed: it duplicated
# `cos hub start --foreground` — both just call web.server.run_server. Dev
# auto-reload lives in `make ui-dev`.)
# ---------------------------------------------------------------------------
try:
    from cli.registry import registry_cli as _registry_cli

    cli.add_command(_registry_cli)

    from cli.hub_commands import hub_cli as _hub_cli, service_cli as _service_cli

    cli.add_command(_hub_cli)
    cli.add_command(_service_cli)
except ImportError as _web_cli_exc:  # pragma: no cover — defensive
    import logging as _logging

    _logging.getLogger("coding_os.cli").debug("web CLI unavailable: %s", _web_cli_exc)


if __name__ == "__main__":
    cli()
