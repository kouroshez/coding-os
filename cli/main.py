#!/usr/bin/env python3
"""
Coding OS — CLI tool for installing and managing the cognitive operating system.

Usage:
    coding-os init --agent claude,codex [--template django]
    coding-os add-adapter codex
    coding-os health
    coding-os eject
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import click
import yaml

from cli._data_types import AggregatedWorld
from cli._init_helpers import (
    InitError,
    ensure_agents_md,
    maybe_git_init,
    resolve_init_target,
)
from cli.adapter_registry import load_adapter_registry
from cli.add_stack import add_stack as add_stack_cmd
from cli.aggregator import aggregate, today_iso
from cli.brain_commands import (
    brain_decay as brain_decay_cmd,
    brain_gc as brain_gc_cmd,
    docs_index as docs_index_cmd,
    graph_reindex as graph_reindex_cmd,
    reindex as reindex_cmd,
    task_sync as task_sync_cmd,
)
from cli.doctor import doctor as doctor_cmd
from cli.eject_file import eject_file as eject_file_cmd
from cli.list_adapters import list_adapters as list_adapters_cmd
from cli.list_stacks import list_stacks as list_stacks_cmd
from cli.setup import setup as setup_cmd
from cli.stack_registry import load_base_profile, load_stack_registry
from cli.update import update as update_cmd

CODING_OS_ROOT = Path(__file__).resolve().parent.parent
ADAPTERS_DIR = CODING_OS_ROOT / "adapters"
CORE_DIR = CODING_OS_ROOT / "core"
TEMPLATES_DIR = CODING_OS_ROOT / "templates"

CONFIG_FILE = ".coding-os.yaml"
STATE_DIR = ".coding-os"


def _discover_valid_agents() -> list[str]:
    """Read adapter ids from adapters/*/adapter.yaml at CLI startup.

    Deliberately separate from `_get_adapter_registry()` because click
    needs a plain list at decorator evaluation time, before module
    initialization has completed. Returns a conservative fallback on
    any load error so the CLI stays bootable.
    """
    try:
        return sorted(load_adapter_registry(ADAPTERS_DIR).keys())
    except Exception:  # noqa: BLE001 — keep CLI bootable on misconfig
        return []


def _discover_valid_templates() -> list[str]:
    """Read stack ids from templates/*/stack.yaml at CLI startup."""
    try:
        return sorted(load_stack_registry(TEMPLATES_DIR).keys())
    except Exception:  # noqa: BLE001
        return []


VALID_AGENTS: list[str] = _discover_valid_agents()
VALID_TEMPLATES: list[str] = _discover_valid_templates()

# Stack and adapter metadata live in templates/*/stack.yaml and
# adapters/*/adapter.yaml. Adding a new stack or adapter is a pure data-file
# change — never touch this module.
#
# The caches below memoize registry loads within a single CLI invocation so
# cos init/doctor/add-stack don't re-parse YAML repeatedly. Tests can reset
# them via _reset_registries_for_tests().

_base_cache = None
_stack_cache = None
_adapter_cache = None


def _get_base_profile():
    global _base_cache
    if _base_cache is None:
        _base_cache = load_base_profile(TEMPLATES_DIR / "_base")
    return _base_cache


def _get_stack_registry():
    global _stack_cache
    if _stack_cache is None:
        _stack_cache = load_stack_registry(TEMPLATES_DIR)
    return _stack_cache


def _get_adapter_registry():
    global _adapter_cache
    if _adapter_cache is None:
        _adapter_cache = load_adapter_registry(ADAPTERS_DIR)
    return _adapter_cache


def _reset_registries_for_tests() -> None:
    """Clear cached registry state. Call from test fixtures that mutate
    templates/ or adapters/ between invocations within a single process."""
    global _base_cache, _stack_cache, _adapter_cache
    _base_cache = None
    _stack_cache = None
    _adapter_cache = None


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
        raise click.ClickException(
            f"adapter '{agent}' not found in {ADAPTERS_DIR}"
        )
    adapter_profile = adapter_registry[agent]

    stack_profiles = []
    for t in templates:
        if t not in stack_registry:
            raise click.ClickException(
                f"stack '{t}' not found — available: {sorted(stack_registry.keys())}"
            )
        stack_profiles.append(stack_registry[t])

    return aggregate(
        base, stack_profiles, adapter_profile, project.name,
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
    """Ask the user which stack templates to apply. Returns a tuple of IDs."""
    registry = _get_stack_registry()
    available = sorted(registry.keys())
    if not available:
        return ()
    click.echo("\nAvailable stacks:")
    for idx, sid in enumerate(available, start=1):
        profile = registry[sid]
        click.echo(f"  {idx}. {sid:10s} — {profile.label}")
    click.echo("  0. none")
    raw = click.prompt(
        "Select stacks (comma-separated numbers or names, e.g. '1,4' or 'django,nextjs')",
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
    # Deduplicate while preserving order.
    seen = set()
    result: list[str] = []
    for s in chosen:
        if s not in seen:
            seen.add(s)
            result.append(s)
    return tuple(result)


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
            f"unknown agent(s): {', '.join(invalid)} "
            f"— available: {', '.join(VALID_AGENTS)}"
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


def _link_stack_skills(
    agent: str,
    templates: tuple[str, ...],
    project_dir: Path,
) -> None:
    """Symlink each applied stack's skills into the agent's skills_dir.

    No-op for adapters whose skills_dir is null (e.g. Codex). Delegates the
    filesystem work to core/scripts/link-stack-skills.sh so the same logic
    is callable from Make targets / cos update.
    """
    registry = _get_adapter_registry()
    if agent not in registry:
        return
    skills_dir = registry[agent].skills_dir
    if not skills_dir:
        return
    linker = CORE_DIR / "scripts" / "link-stack-skills.sh"
    if not linker.exists():
        click.echo(f"  WARN: stack-skill linker missing: {linker}", err=True)
        return
    agent_skills_abs = str(project_dir / skills_dir)
    result = subprocess.run(
        ["bash", str(linker), agent_skills_abs, str(CODING_OS_ROOT), *templates],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        click.echo(
            f"  WARN: stack-skill linking failed:\n{result.stderr}",
            err=True,
        )
        return
    linked = []
    for t in templates:
        stack_skills = CODING_OS_ROOT / "templates" / t / "skills"
        if stack_skills.exists():
            linked.extend(sorted(p.name for p in stack_skills.iterdir() if p.is_dir()))
    if linked:
        click.echo(f"  Linked stack skills: {', '.join(linked)}")


def _run_adapter_install(agent: str, project_dir: Path) -> None:
    """Run the adapter's declared install script.

    Uses adapter.yaml::install_script so a new adapter is pure data — no
    hardcoded path assumption.
    """
    registry = _get_adapter_registry()
    if agent not in registry:
        click.echo(
            f"  ERROR: Unknown adapter '{agent}' — available: "
            f"{sorted(registry.keys())}",
            err=True,
        )
        sys.exit(1)
    install_script = registry[agent].install_script
    if not install_script.exists():
        click.echo(
            f"  ERROR: Adapter install script not found: {install_script}",
            err=True,
        )
        sys.exit(1)

    result = subprocess.run(
        ["bash", str(install_script)],
        cwd=str(project_dir),
        capture_output=True,
        text=True,
    )
    if result.stdout:
        click.echo(result.stdout)
    if result.returncode != 0:
        click.echo(f"  ERROR: Adapter install failed:\n{result.stderr}", err=True)
        sys.exit(1)


def _apply_template(
    template_name: str,
    project_dir: Path,
    agent: str | None = None,
) -> None:
    """Apply a stack template to the project.

    1. Copies `templates/<name>/{rules,skills,playbooks,hooks}/` to
       `<project>/.coding-os/templates/<name>/…` for browsing.
    2. If `agent` is provided and that adapter supports path-scoped rules
       (`adapter.rules_dir` != null), also copies every
       `templates/<name>/rules/*.md` into the adapter's rules dir with a
       `<stack>-<filename>` prefix so multiple stacks coexist.
    """
    stack_registry = _get_stack_registry()
    if template_name not in stack_registry:
        click.echo(
            f"  WARN: Template '{template_name}' not in registry "
            f"(available: {sorted(stack_registry.keys())})",
            err=True,
        )
        return
    stack_profile = stack_registry[template_name]
    template_dir = stack_profile.source_dir

    # 1. Mirror every subdir into .coding-os/templates/<name>/
    for subdir in ("rules", "skills", "playbooks", "hooks"):
        src = template_dir / subdir
        if src.exists():
            dest = project_dir / STATE_DIR / "templates" / template_name / subdir
            dest.mkdir(parents=True, exist_ok=True)
            for item in src.iterdir():
                if item.is_file():
                    shutil.copy2(item, dest / item.name)
                elif item.is_dir():
                    shutil.copytree(item, dest / item.name, dirs_exist_ok=True)

    # 2. Copy path-scoped rules into the adapter's rules_dir (if supported).
    if agent is not None:
        adapters = _get_adapter_registry()
        if agent in adapters:
            adapter_profile = adapters[agent]
            if adapter_profile.supports_rules and adapter_profile.rules_dir:
                rules_src = template_dir / "rules"
                if rules_src.exists():
                    rules_dest = project_dir / adapter_profile.rules_dir
                    rules_dest.mkdir(parents=True, exist_ok=True)
                    for rule_file in sorted(rules_src.glob("*.md")):
                        # Prefix with stack id to avoid collisions between stacks.
                        out = rules_dest / f"{template_name}-{rule_file.name}"
                        shutil.copy2(rule_file, out)
            elif not adapter_profile.supports_rules:
                click.echo(
                    f"  INFO: adapter '{agent}' does not support path-scoped "
                    f"rules — skipping rules copy for '{template_name}'",
                )

    click.echo(f"  Template '{template_name}' applied.")


# _merge_profiles, _build_substitutions, _list_installed_skills have all
# been replaced by the aggregator pipeline. See _build_world() above and
# cli/aggregator.py::aggregate() for the data-driven replacement.


def _resolve_placeholders(text: str, substitutions: dict[str, str]) -> str:
    """Replace `{{KEY}}` placeholders. Unknown keys are left intact for later overlay."""
    result = text
    for key, value in substitutions.items():
        result = result.replace(f"{{{{{key}}}}}", value)
    return result


def _overlay_scaffold(
    project: Path,
    templates: tuple[str, ...],
    substitutions: dict[str, str],
) -> int:
    """Copy `_base/scaffold/` then each template's `scaffold/` into `project/`.

    Existing project files are NEVER overwritten (idempotent init).
    Markdown files have their `{{KEY}}` placeholders resolved.

    Returns: count of files copied.
    """
    # Source roots in overlay order: _base first, then each template overlay.
    sources: list[Path] = [TEMPLATES_DIR / "_base" / "scaffold"]
    for name in templates:
        candidate = TEMPLATES_DIR / name / "scaffold"
        if candidate.exists():
            sources.append(candidate)

    copied = 0
    for src_root in sources:
        if not src_root.exists():
            continue
        for src_file in src_root.rglob("*"):
            if not src_file.is_file():
                continue
            if src_file.name == ".gitkeep":
                # .gitkeep just ensures the parent dir exists in the copy.
                rel = src_file.relative_to(src_root)
                dest = project / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                continue

            rel = src_file.relative_to(src_root)
            dest = project / rel
            if dest.exists():
                # Idempotent: never overwrite existing project files.
                continue

            dest.parent.mkdir(parents=True, exist_ok=True)
            if src_file.suffix == ".md":
                content = src_file.read_text(encoding="utf-8")
                content = _resolve_placeholders(content, substitutions)
                dest.write_text(content, encoding="utf-8")
            else:
                shutil.copy2(src_file, dest)
            copied += 1

    return copied


def _copy_workflow_docs(project: Path) -> None:
    """Copy thinking_os-final-edition.md from core/docs/ into project workflow-docs/.

    The full thinking_os reference is too large (57KB, 1439 lines) to duplicate
    in the scaffold dir. Instead, we copy it from core/docs/ at init time.
    """
    src = CORE_DIR / "docs" / "thinking_os-final-edition.md"
    if not src.exists():
        return
    dest = project / "docs" / "workflow-docs" / "thinking_os-final-edition.md"
    if dest.exists():
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)


def _bootstrap_hub_dir_if_first_run() -> None:
    """Seed ~/.coding-os/ the very first time the CLI is invoked.

    PURPOSE: Close the install UX gap — after `uv tool install coding-os`
             the hub dir didn't exist until a user ran a command that
             happened to touch it.  Creating the directory eagerly (and
             an empty registry.json) means `cos hub start` and the
             /api/hub/* endpoints behave deterministically from the
             first command.
    NOTES:   Fail-open: any OSError is silently swallowed.  We never
             raise from the entry point because a home-dir permission
             quirk shouldn't break every `cos ...` call.
             Respects COS_REGISTRY_PATH so tests with custom paths are
             untouched.
    """
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


@click.group()
@click.version_option(version="0.2.0", prog_name="coding-os")
def cli() -> None:
    """Coding OS — Agent-agnostic cognitive operating system for AI coding agents."""
    _bootstrap_hub_dir_if_first_run()


cli.add_command(doctor_cmd)
cli.add_command(list_stacks_cmd)
cli.add_command(list_adapters_cmd)
cli.add_command(add_stack_cmd)
cli.add_command(docs_index_cmd)
cli.add_command(task_sync_cmd)
cli.add_command(reindex_cmd)
cli.add_command(graph_reindex_cmd)
cli.add_command(brain_decay_cmd)
cli.add_command(brain_gc_cmd)
cli.add_command(update_cmd)
cli.add_command(setup_cmd)
cli.add_command(eject_file_cmd)

# Phase O.1 — Hub propagation: push meta-repo edits to every registered
# project via symlink re-link + DB migration.  Lives in cli/sync_all.py
# so registry.py stays focused on the JSON CRUD.
try:
    from cli.sync_all import sync_all_cmd, sync_doctor_cmd
    cli.add_command(sync_all_cmd)
    cli.add_command(sync_doctor_cmd)
except ImportError as _e:  # noqa: BLE001 — optional if cli.main is imported early
    import logging as _logging
    _logging.getLogger("cli.main").debug("sync_all unavailable: %s", _e)

# Phase L.6 — board_os CLI surface (16 commands).
try:
    from cli.board_commands import BOARD_COMMANDS
    for _bc in BOARD_COMMANDS:
        cli.add_command(_bc)
except ImportError:
    pass  # board_os optional — don't break `cos` if deps missing.

# Phase M — cognition CLI (formula dispatches, persona selections, backtracks).
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
    Detect this by checking for the telltale `core/thinking_os/server.py`
    file and refuse.
    """
    marker = project / "core" / "thinking_os" / "server.py"
    cli_main = project / "cli" / "main.py"
    if marker.exists() and cli_main.exists():
        click.echo(
            f"\nERROR: Refusing to init inside the coding-os repo itself ({project}).\n"
            f"  This path contains core/thinking_os/server.py — it is the source tree.\n"
            f"  Initializing here would scatter scaffold files into the repo.\n\n"
            f"  Fix:\n"
            f"    cd /path/to/your/actual-project\n"
            f"    uv run --directory {project} python -m cli.main init \\\n"
            f"      --agent claude --project-dir \"$(pwd)\"\n\n"
            f"  Or use the alias:\n"
            f"    alias cos-init='uv run --directory {project} python -m cli.main init'\n"
            f"    cos-init --agent claude --project-dir \"$(pwd)\"\n",
            err=True,
        )
        sys.exit(1)


@cli.command()
@click.option("--agent", "-a", default=None, help="Agent adapter(s) to install, comma-separated (e.g. 'claude,codex'). Prompted if omitted (unless --yes).")
@click.option("--template", "-t", multiple=True, help="Stack template(s) to apply")
@click.option("--project-dir", "-d", default=None, help="Parent directory for the project (default: shell cwd). Mutually exclusive with --debug.")
@click.option("--name", "-n", default=None, help="Create a new directory with this name inside --project-dir (or cwd). Validated: ^[a-z0-9][a-z0-9._-]{0,63}$")
@click.option("--debug", is_flag=True, default=False, help="Scaffold into <coding-os>/.build/debug/<name>/ (or 'the-script-output'). Requires running inside the coding-os repo.")
@click.option("--git/--no-git", default=True, help="Run `git init` in the new project (default: --git). Skipped silently if target is nested in an existing git repo.")
@click.option("--force", is_flag=True, default=False, help="Overwrite target directory if it already exists and is non-empty.")
@click.option("--yes", "-y", is_flag=True, default=False, help="Non-interactive: use defaults for anything not passed via flags. Required in CI / non-TTY.")
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text", help="Output format.")
@click.option("--today", "today_override", default=None, help="ISO-8601 date to use for {{DATE}} substitutions (default: today). Deterministic fixture for golden tests.")
def init(
    agent: str | None,
    template: tuple[str, ...],
    project_dir: str | None,
    name: str | None,
    debug: bool,
    git: bool,
    force: bool,
    yes: bool,
    output_format: str,
    today_override: str | None,
) -> None:
    """Initialize coding-os in a project.

    Interactive by default — prompts for missing agent/template/name when a
    TTY is attached. Pass --yes for fully non-interactive runs (CI) using
    whatever flags are provided plus sensible defaults.
    """
    shell_cwd_raw = os.environ.get("PWD") or os.getcwd()
    shell_cwd = Path(shell_cwd_raw).resolve()

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

    _scaffold_buffer = io.StringIO()
    _stdout_redirect = (
        contextlib.redirect_stdout(_scaffold_buffer)
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
        _run_scaffold_phase(agents, template, project, today=today_override)

    git_result = maybe_git_init(target, enabled=git)
    files_created = sum(1 for _ in project.rglob("*") if _.is_file())

    summary: dict[str, object] = {
        "status": "ok",
        "path": str(project),
        "agents": agents,
        "templates": list(template),
        "debug": debug,
        "forced_empty": target.forced_empty,
        "git": {
            "ran": git_result.ran,
            "skipped_reason": git_result.skipped_reason,
            "error": git_result.error,
        },
        "files_created": files_created,
        "db_path": str(project / STATE_DIR / "thinking_os.db"),
        "config_file": str(project / CONFIG_FILE),
    }

    if output_format == "json":
        click.echo(json.dumps(summary, indent=2))
        return

    # text mode — final summary
    if git_result.ran:
        click.echo("  git: initialized")
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
    click.echo("\nQuick start:")
    click.echo("  make session-init    # See project status")
    click.echo("  make task-next       # See next task")
    click.echo("  make task-start TASK=001  # Start working")


def _run_scaffold_phase(
    agents: list[str],
    template: tuple[str, ...],
    project: Path,
    *,
    today: str | None = None,
) -> None:
    """Original scaffolding body — extracted so it can be redirected in JSON mode.

    `today` is an optional ISO-8601 override for {{DATE}} substitution
    in scaffolded files (used by golden parity tests for determinism).
    """

    # 1. Create state directory
    state = project / STATE_DIR
    state.mkdir(parents=True, exist_ok=True)
    click.echo(f"  Created {STATE_DIR}/")

    # 2. Initialize DB directory
    db_path = state / "thinking_os.db"
    if not db_path.exists():
        # Initialize the database
        brain_dir = str(CORE_DIR / "thinking_os")
        init_code = (
            "import sys; "
            f"sys.path.insert(0, {brain_dir!r}); "
            "from db import init_db; "
            f"init_db({str(db_path)!r})"
        )
        env = os.environ.copy()
        env["COS_DB_PATH"] = str(db_path)
        subprocess.run(
            [sys.executable, "-c", init_code],
            env=env,
            capture_output=True,
        )
        click.echo("  Initialized thinking_os database")

    # 3. Generate config
    config = {
        "version": "1.0",
        "agents": agents,
        "templates": list(template),
        "state_dir": STATE_DIR,
        "code_extensions": ["py", "ts", "tsx", "js", "jsx"],
        "verify": {},
        "protected_files": [],
    }
    _save_config(project, config)
    click.echo(f"  Generated {CONFIG_FILE}")

    # 4. Run adapter install for each agent
    for agent in agents:
        click.echo(f"\nInstalling {agent} adapter...")
        _run_adapter_install(agent, project)

    # 5. Apply templates (agent-agnostic content first)
    for t in template:
        click.echo(f"\nApplying template: {t}")
        # Pass first agent for path-scoped rules; additional agents get
        # rules via their own adapter install or add-adapter.
        _apply_template(t, project, agent=agents[0])

    # 5b. Link stack-scoped skills into each agent's skills_dir.
    if template:
        for agent in agents:
            _link_stack_skills(agent, template, project)

    # 6. Aggregate base + stacks + adapter into a world.
    # Use the first agent for world building (substitutions, AGENTS.md).
    # All adapters share the same core content; adapter-specific setup
    # was handled in step 4.
    for w in _get_stack_registry().warnings:
        click.echo(f"  WARN: {w}", err=True)
    world = _build_world(agents[0], template, project, today=today)
    for msg in world.conflicts:
        click.echo(f"  WARN: {msg}", err=True)
    substitutions = world.substitutions

    # 6b. Patch .coding-os.yaml.verify with derived commands.
    # step 3 wrote an empty dict because the world is only available here.
    # enforce-verify.sh reads this map to know which suite to require per
    # changed-file glob, so we must populate it before any hook runs.
    verify_map = _derive_verify_from_world(world)
    if verify_map:
        existing = _load_config(project) or {}
        existing["verify"] = verify_map
        _save_config(project, existing)
        click.echo(f"  Populated verify config: {', '.join(sorted(verify_map))}")

    # 7. Overlay scaffold files (_base + each template overlay) with placeholder resolution
    copied = _overlay_scaffold(project, template, substitutions)
    if copied:
        click.echo(f"  Copied {copied} scaffold file(s) (docs/, governance/, playbooks/, ...)")

    # 8. Copy thinking_os reference doc from core/docs/
    _copy_workflow_docs(project)

    # 9. Copy Makefile.base verbatim. The `cos` CLI binary (installed
    # via `uv tool install`) owns path discovery — Makefile.base calls
    # `cos docs-index`, `cos task-sync`, etc. and stays fully portable.
    makefile_src = TEMPLATES_DIR / "_base" / "Makefile.base"
    if makefile_src.exists():
        makefile_dest = state / "Makefile.base"
        shutil.copy2(makefile_src, makefile_dest)
        click.echo(f"  Copied Makefile.base to {STATE_DIR}/")

        # Create a project Makefile if none exists
        project_makefile = project / "Makefile"
        if not project_makefile.exists():
            project_makefile.write_text(
                f"# Project Makefile\n"
                f"# coding-os universal targets\n"
                f"include {STATE_DIR}/Makefile.base\n\n"
                f"# Add your project-specific targets below:\n\n"
            )
            click.echo("  Generated Makefile")

    # 10. Generate AGENTS.md by composing fragments from base + stacks.
    # No template file is read; the content is assembled by render_agents_md()
    # from the fragments registered in base.yaml::agents_md_sections (and any
    # fragments stacks contribute via their own stack.yaml::agents_md_sections).
    if ensure_agents_md(project, world):
        click.echo("  Generated AGENTS.md")

    # 11. Register project in the global ~/.coding-os/registry.json so the
    # Hub web UI (`cos hub`) can enumerate it and serve its sqlite DB.
    try:
        from cli.registry import add_project as _registry_add_project

        entry = _registry_add_project(project)
        click.echo(f"  Registered in hub registry: {entry.slug}")
    except Exception as exc:  # noqa: BLE001
        # Registry is non-fatal — a failed write should not break init.
        click.echo(f"  WARN: could not register project in hub registry: {exc}", err=True)


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
        snippet = (
            "\n[mcp_servers.coding-os]\n"
            'command = "cos"\n'
            'args = ["server-start"]\n'
        )
        command = "cos"
        args = ["server-start"]
    else:
        server_py = (CODING_OS_ROOT / "core" / "thinking_os" / "server.py").as_posix()
        python = sys.executable
        snippet = (
            "\n[mcp_servers.coding-os]\n"
            f'command = "{python}"\n'
            f'args = ["{server_py}"]\n'
        )
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
            proc.stderr.strip()
            or f"failed to configure coding-os MCP in {target}"
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
        click.echo(f"  State dir:  MISSING")

    # Database
    db_path = state / "thinking_os.db"
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
def eject(project_dir: str) -> None:
    """Convert symlinks to real files (self-contained project)."""
    project = _resolve_project_dir(project_dir)
    ejected = 0

    for root, dirs, files in os.walk(project):
        for name in files:
            filepath = Path(root) / name
            if filepath.is_symlink():
                target = filepath.resolve()
                if target.exists():
                    filepath.unlink()
                    shutil.copy2(target, filepath)
                    ejected += 1

    click.echo(f"Ejected {ejected} symlinks to real files.")
    click.echo("Project is now self-contained.")


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
def hooks_log(
    project_dir: str,
    tail_count: int,
    follow: bool,
    agent: str | None,
    session: str | None,
    task: str | None,
    hook: str | None,
) -> None:
    """Show recent hook activity from .coding-os/.hooks.log.

    Hooks call `cos_log_hook` (from core/hooks/cos-env.sh) on fire / block /
    allow / warn. Every line carries `agent=X session=Y task=Z` identity
    fields so you can filter by any combination:

        cos hooks-log --agent claude                   # only claude runs
        cos hooks-log --session ses-20260418-143638-c769
        cos hooks-log --task governance-mcp-envelope --hook enforce-
        cos hooks-log --agent codex --follow           # live codex stream

    Filters are AND-ed together and use substring match (case-sensitive).
    """
    project = _resolve_project_dir(project_dir)
    config = _load_config(project) or {}
    state = project / config.get("state_dir", STATE_DIR)
    log_path = state / ".hooks.log"

    if not log_path.exists():
        click.echo(f"No hook activity yet ({log_path} does not exist).")
        click.echo("Hint: hooks log on fire — if you expected events, check"
                   " .claude/settings.json or .codex/hooks.json wiring.")
        return

    filters: list[str] = []
    if agent:
        filters.append(f"agent={agent}")
    if session:
        filters.append(f"session={session}")
    if task:
        filters.append(f"task={task}")
    if hook:
        filters.append(f"[{hook}")

    if not filters:
        cmd = ["tail"] + (["-f"] if follow else []) + ["-n", str(tail_count), str(log_path)]
        subprocess.run(cmd)
        return

    if follow:
        tail_cmd = f"tail -f -n {tail_count} {shlex.quote(str(log_path))}"
        grep_chain = " | ".join(
            f"grep -F --line-buffered {shlex.quote(f)}" for f in filters
        )
        subprocess.run(["bash", "-c", f"{tail_cmd} | {grep_chain}"])
        return

    try:
        lines = log_path.read_text(errors="replace").splitlines()
    except OSError as exc:
        click.echo(f"Could not read {log_path}: {exc}", err=True)
        return
    matched = [ln for ln in lines if all(f in ln for f in filters)]
    for ln in matched[-tail_count:]:
        click.echo(ln)


@cli.command("hooks-list")
@click.option("--agent", type=str, default=None, help="Filter by adapter (claude|codex)")
@click.option("--category", type=str, default=None, help="Filter by category")
@click.option("--phase", type=str, default=None, help="Filter by phase")
def hooks_list(agent: str | None, category: str | None, phase: str | None) -> None:
    """List hooks registered in core/hooks/registry.yaml with filters.

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
                f"{e['event']}::{e.get('matcher', '')}".rstrip(":")
                for e in h.events
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
        str(caller_cwd / STATE_DIR / "thinking_os.db"),
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


# ---------------------------------------------------------------------------
# Phase I — graph_os subcommand family (`cos graph-*`).
# Registration lives in cli/graph_commands.py so the main file stays lean.
# ---------------------------------------------------------------------------
try:
    from cli import graph_commands as _graph_commands  # noqa: WPS433

    _graph_commands.register(cli)
except ImportError as _graph_cli_exc:  # pragma: no cover — defensive
    import logging as _logging

    _logging.getLogger("coding_os.cli").debug(
        "graph_os CLI unavailable: %s", _graph_cli_exc
    )


# ---------------------------------------------------------------------------
# S4 — unified web server CLI (`cos web`).
# ---------------------------------------------------------------------------
try:
    from cli.web_commands import web_cmd as _web_cmd  # noqa: WPS433

    cli.add_command(_web_cmd)

    from cli.registry import registry_cli as _registry_cli  # noqa: WPS433

    cli.add_command(_registry_cli)

    from cli.hub_commands import hub_cli as _hub_cli, service_cli as _service_cli  # noqa: WPS433

    cli.add_command(_hub_cli)
    cli.add_command(_service_cli)
except ImportError as _web_cli_exc:  # pragma: no cover — defensive
    import logging as _logging

    _logging.getLogger("coding_os.cli").debug(
        "web CLI unavailable: %s", _web_cli_exc
    )


if __name__ == "__main__":
    cli()
