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
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import click
import yaml

from cli._data_types import AggregatedWorld
from cli._resources import adapters_dir, core_dir, data_root, templates_dir
from cli._init_helpers import (
    InitError,
    ensure_agents_md,
    ensure_gitignore,
    install_consumer_git_hooks,
    maybe_git_init,
    maybe_initial_commit,
    resolve_init_target,
)
from cli.adapter_registry import load_adapter_registry
from cli.add_stack import add_stack as add_stack_cmd
from cli.remove_stack import remove_stack as remove_stack_cmd
from cli.config_composer import COMPOSED_FILENAMES, compose_coding_os_configs
from cli.aggregator import aggregate, today_iso
from cli.brain_commands import (
    brain_decay as brain_decay_cmd,
    brain_gc as brain_gc_cmd,
    docs_index as docs_index_cmd,
    graph_reindex as graph_reindex_cmd,
    reindex as reindex_cmd,
    task_sync as task_sync_cmd,
)
from cli.core_version import stamp_core_version
from cli.doctor import doctor as doctor_cmd
from cli.eject_file import eject_file as eject_file_cmd
from cli.list_adapters import list_adapters as list_adapters_cmd
from cli.list_stacks import list_stacks as list_stacks_cmd
from cli.setup import setup as setup_cmd
from cli.skills_list import skills_list as skills_list_cmd
from cli.stack_registry import (
    load_base_profile,
    load_stack_registry,
    resolve_relocated_profiles,
    service_relocations,
)
from cli.tail_command import tail_cmd
from cli.update import update as update_cmd

# CODING_OS_ROOT is the source-checkout root — kept for dev-only operations; it
# is meaningless under a wheel install. The bundled DATA trees resolve via
# importlib so they are found under both src-layout and wheel installs (TASK-219).
CODING_OS_ROOT = Path(__file__).resolve().parent.parent.parent
ADAPTERS_DIR = adapters_dir()
CORE_DIR = core_dir()
TEMPLATES_DIR = templates_dir()

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
    except Exception:
        return []


def _discover_valid_templates() -> list[str]:
    """Read stack ids from templates/*/stack.yaml at CLI startup."""
    try:
        return sorted(load_stack_registry(TEMPLATES_DIR).keys())
    except Exception:
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
        raise click.ClickException(f"adapter '{agent}' not found in {ADAPTERS_DIR}")
    adapter_profile = adapter_registry[agent]

    for t in templates:
        if t not in stack_registry:
            raise click.ClickException(
                f"stack '{t}' not found — available: {sorted(stack_registry.keys())}"
            )
    # Colliding structure.roots are relocated to src/services/<id> BEFORE
    # aggregation so every derived artifact is service-scoped
    # (project-anatomy.md § Glob/verify propagation, TASK-355).
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
    profiles = {sid: registry[sid] for sid in registry.keys()}
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


def _link_stack_skills(
    agent: str,
    templates: tuple[str, ...],
    project_dir: Path,
) -> None:
    """Symlink each applied stack's skills into the agent's skills_dir.

    No-op for adapters whose skills_dir is null (e.g. Codex). Delegates the
    filesystem work to src/core/scripts/link-stack-skills.sh so the same logic
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
        ["bash", str(linker), agent_skills_abs, str(data_root()), *templates],
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
        stack_skills = templates_dir(t, "skills")
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
            f"  ERROR: Unknown adapter '{agent}' — available: {sorted(registry.keys())}",
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

    1. Copies `src/templates/<name>/{rules,skills,playbooks,hooks}/` to
       `<project>/.coding-os/templates/<name>/…` for browsing.
    2. If `agent` is provided and that adapter supports path-scoped rules
       (`adapter.rules_dir` != null), also copies every
       `src/templates/<name>/rules/*.md` into the adapter's rules dir with a
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
            dest = project_dir / STATE_DIR / "src" / "templates" / template_name / subdir
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
# src/cli/aggregator.py::aggregate() for the data-driven replacement.


# Scaffold text files whose {{KEY}} placeholders are resolved at copy time.
# Unknown keys are always left intact, so files with no placeholders are
# byte-identical after the pass (plain-stack code skeletons need this —
# go.mod / main.go / index.ts carry {{PROJECT_NAME}}; TASK-348).
_PLACEHOLDER_SUFFIXES = {".md", ".go", ".mod", ".ts", ".tsx", ".json", ".vue"}


def _resolve_placeholders(text: str, substitutions: dict[str, str]) -> str:
    """Replace `{{KEY}}` placeholders. Unknown keys are left intact for later overlay."""
    result = text
    for key, value in substitutions.items():
        result = result.replace(f"{{{{{key}}}}}", value)
    return result


# Tag-driven docs composition (TASK-360):
#  - file-level: a `module:<id>` token in the first-line header comment skips
#    the whole doc when that module is disabled;
#  - block-level: `<!-- if-stack:a,b -->` / `<!-- if-module:docs -->` ...
#    `<!-- end-if -->` keep the block only when ANY listed stack is installed /
#    the module is enabled. Markers and tags are stripped from the copy, so a
#    fully-default project's output is byte-identical to untagged sources.
_DOC_MODULE_TAG_RE = re.compile(r"\s*\|\s*module:([a-z][a-z0-9_-]*)")
_DOC_IF_RE = re.compile(r"^<!--\s*if-(stack|module):([a-z0-9_,-]+)\s*-->\s*$")
_DOC_ENDIF_RE = re.compile(r"^<!--\s*end-if\s*-->\s*$")


def _apply_doc_conditions(
    text: str, disabled_modules: set[str], active_stacks: set[str]
) -> tuple[bool, str]:
    """(skip_file, transformed_text) — see the marker contract above."""
    lines = text.split("\n")
    if lines:
        tag = _DOC_MODULE_TAG_RE.search(lines[0])
        if tag and lines[0].lstrip().startswith("<!--"):
            if tag.group(1) in disabled_modules:
                return True, ""
            lines[0] = _DOC_MODULE_TAG_RE.sub("", lines[0], count=1)

    out: list[str] = []
    keeping = True
    in_block = False
    for line in lines:
        opener = _DOC_IF_RE.match(line)
        if opener and not in_block:
            in_block = True
            kind, raw_ids = opener.group(1), opener.group(2)
            wanted = {x for x in raw_ids.split(",") if x}
            if kind == "stack":
                keeping = bool(wanted & active_stacks)
            else:
                keeping = not (wanted & disabled_modules)
            continue
        if _DOC_ENDIF_RE.match(line) and in_block:
            in_block = False
            keeping = True
            continue
        if keeping:
            out.append(line)
    return False, "\n".join(out)


def _dry_config_preview(templates: tuple[str, ...], output_format: str) -> None:
    """`cos init --dry-config` — merged .coding-os preview, zero writes."""
    from cli.config_composer import preview_coding_os_configs

    merged, conflicts = preview_coding_os_configs(list(templates), templates_dir=TEMPLATES_DIR)
    if output_format == "json":
        click.echo(
            json.dumps(
                {"stacks": list(templates), "configs": merged, "conflicts": conflicts},
                indent=2,
                ensure_ascii=False,
            )
        )
        return
    scrumban = merged.get("scrumban-config.yaml") or {}
    lanes = [
        lane.get("id") for lane in scrumban.get("swimlanes") or [] if isinstance(lane, dict)
    ]
    click.echo(f"Merge preview for stacks: {', '.join(templates) or '(base only)'}")
    click.echo(f"  swimlanes: {', '.join(lanes) or '(none)'}")
    for filename in merged:
        click.echo(f"  composed: {filename}")
    if conflicts:
        click.echo(f"  conflicts ({len(conflicts)} — later wins):")
        for line in conflicts:
            click.echo(f"    WARN: {line}")
    else:
        click.echo("  conflicts: none")
    click.echo("(dry-config — nothing written)")


def _service_relocations(templates: tuple[str, ...]) -> dict[str, str]:
    """stack-id → relocated root for stacks whose structure.root collides.

    Thin wrapper over the SSOT in cli.stack_registry (shared with
    cli.update._aggregate_world); see project-anatomy.md.
    """
    return service_relocations(_get_stack_registry(), templates)


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
    # Each entry: (scaffold dir, owning stack id or None for _base).
    sources: list[tuple[Path, str | None]] = [(TEMPLATES_DIR / "_base" / "scaffold", None)]
    for name in templates:
        candidate = TEMPLATES_DIR / name / "scaffold"
        if candidate.exists():
            sources.append((candidate, name))

    relocations = _service_relocations(templates)
    registry = _get_stack_registry()

    from cli.subsystems import module_state

    disabled_modules = {
        module_id for module_id, enabled in module_state(project).items() if not enabled
    }
    active_stacks = set(templates)

    copied = 0
    for src_root, stack_id in sources:
        if not src_root.exists():
            continue
        relocated_root = relocations.get(stack_id) if stack_id else None
        declared_root = (
            (registry[stack_id].structure or {}).get("root", "").rstrip("/")
            if stack_id and stack_id in registry.keys()
            else ""
        )
        for src_file in src_root.rglob("*"):
            if not src_file.is_file():
                continue
            if src_file.name == ".gitkeep":
                # .gitkeep just ensures the parent dir exists in the copy —
                # honoring service relocation like any other scaffold path.
                rel = src_file.relative_to(src_root)
                if relocated_root and declared_root and str(rel).startswith(declared_root + "/"):
                    rel = Path(relocated_root) / str(rel)[len(declared_root) + 1 :]
                dest = project / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                continue

            rel = src_file.relative_to(src_root)
            if relocated_root and declared_root and str(rel).startswith(declared_root + "/"):
                rel = Path(relocated_root) / str(rel)[len(declared_root) + 1 :]
            if rel.parent.name == ".coding-os" and rel.name in COMPOSED_FILENAMES:
                # These are deep-merged from base + every stack by
                # compose_coding_os_configs — overlaying base first would
                # shadow the merge (first-writer-wins). See config-composition.md.
                continue
            dest = project / rel
            if dest.exists():
                # Idempotent: never overwrite existing project files.
                continue

            dest.parent.mkdir(parents=True, exist_ok=True)
            if src_file.suffix in _PLACEHOLDER_SUFFIXES:
                content = src_file.read_text(encoding="utf-8")
                content = _resolve_placeholders(content, substitutions)
                if src_file.suffix == ".md":
                    skip_file, content = _apply_doc_conditions(
                        content, disabled_modules, active_stacks
                    )
                    if skip_file:
                        continue
                dest.write_text(content, encoding="utf-8")
            else:
                shutil.copy2(src_file, dest)
            copied += 1

    return copied


def _aggregate_scaffold_boundaries(
    project: Path,
    state: Path,
    templates: list[str],
) -> None:
    """Merge per-stack `scaffold-boundary.yaml` files into the consumer."""
    import yaml

    stacks_data: list[dict] = []
    for stack_id in templates:
        boundary_src = TEMPLATES_DIR / stack_id / "scaffold-boundary.yaml"
        if not boundary_src.exists():
            continue
        try:
            data = yaml.safe_load(boundary_src.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise click.ClickException(
                f"src/templates/{stack_id}/scaffold-boundary.yaml is not valid YAML: {exc}"
            )
        if not isinstance(data, dict):
            continue
        stacks_data.append(
            {
                "stack": data.get("stack") or stack_id,
                "roots": list(data.get("roots") or []),
                "file_patterns": list(data.get("file_patterns") or []),
                "imports_from": list(data.get("imports_from") or []),
                "forbids_writing_in": list(data.get("forbids_writing_in") or []),
            }
        )

    target = state / "scaffold-boundary.yaml"
    if not stacks_data:
        if target.exists():
            target.unlink()
        return

    # Multi-backend relocation (project-anatomy.md): colliding declared roots
    # move each stack's boundary to src/services/<stack-id>/ BEFORE the
    # shared-root invariant — composed backends coexist by design.
    relocations = _service_relocations(tuple(templates))
    if relocations:
        registry = _get_stack_registry()
        for entry in stacks_data:
            new_root = relocations.get(entry["stack"])
            if not new_root or entry["stack"] not in registry.keys():
                continue
            declared = (registry[entry["stack"]].structure or {}).get("root", "").rstrip("/")
            if not declared:
                continue

            def _remap(path: str) -> str:
                stripped = path.rstrip("/")
                if stripped == declared or stripped.startswith(declared + "/"):
                    remapped = new_root + stripped[len(declared) :]
                    return remapped + "/" if path.endswith("/") else remapped
                return path

            entry["roots"] = [_remap(r) for r in entry["roots"]]
            entry["file_patterns"] = [_remap(p) for p in entry["file_patterns"]]

        # Cross-service walls: each relocated root becomes forbidden to every
        # OTHER stack, so an unowned write into a sibling service is flagged
        # (project-anatomy.md § Glob/verify propagation — parameterized, never
        # hand-listed in any stack's scaffold-boundary.yaml).
        for entry in stacks_data:
            for other_id, other_root in relocations.items():
                wall = other_root.rstrip("/") + "/"
                if other_id != entry["stack"] and wall not in entry["forbids_writing_in"]:
                    entry["forbids_writing_in"].append(wall)

    # Invariant 1: no two installed stacks may share a root.
    seen: dict[str, str] = {}
    for entry in stacks_data:
        for root in entry["roots"]:
            existing = seen.get(root)
            if existing and existing != entry["stack"]:
                raise click.ClickException(
                    f"scaffold-boundary aggregation: root '{root}' claimed by "
                    f"both '{existing}' and '{entry['stack']}'. Two installed "
                    f"stacks may not share a root — pick one per project."
                )
            seen[root] = entry["stack"]

    # Invariant 2: every forbid references an installed root OR `shared/`.
    all_roots = {root.rstrip("/") for root in seen}
    all_roots.add("shared")
    for entry in stacks_data:
        for forbidden in entry["forbids_writing_in"]:
            stripped = forbidden.rstrip("/")
            if stripped not in all_roots:
                # Soft: mention but do not fail — a stack may legitimately
                # forbid a subtree no installed stack owns yet.
                click.echo(
                    f"  WARN: stack '{entry['stack']}' forbids writes in "
                    f"'{forbidden}', but no installed stack owns that root.",
                    err=True,
                )

    aggregated = {
        "version": 1,
        "generated_by": "src/cli/_aggregate_scaffold_boundaries",
        "stacks": stacks_data,
    }
    target.write_text(
        yaml.safe_dump(aggregated, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )
    click.echo(
        f"  Aggregated scaffold-boundary for {len(stacks_data)} stack(s) → {target.relative_to(project)}"
    )


def _copy_workflow_docs(project: Path) -> None:
    """Copy thinking_os-final-edition.md from src/core/docs/ into project workflow/.

    The full thinking_os reference is too large (57KB, 1439 lines) to duplicate
    in the scaffold dir. Instead, we copy it from src/core/docs/ at init time.
    """
    src = CORE_DIR / "docs" / "thinking_os-final-edition.md"
    if not src.exists():
        return
    dest = project / "docs" / "workflow" / "thinking_os-final-edition.md"
    if dest.exists():
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)


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
cli.add_command(graph_reindex_cmd)
cli.add_command(brain_decay_cmd)
cli.add_command(brain_gc_cmd)
cli.add_command(update_cmd)
cli.add_command(setup_cmd)
cli.add_command(eject_file_cmd)
cli.add_command(tail_cmd)
cli.add_command(skills_list_cmd)

from cli.module_commands import module_group as module_group_cmd  # noqa: E402
from cli.preset_commands import preset_group as preset_group_cmd  # noqa: E402
from cli.stack_lint import stack_lint as stack_lint_cmd  # noqa: E402

cli.add_command(module_group_cmd)
cli.add_command(preset_group_cmd)
cli.add_command(stack_lint_cmd)

# Durable error/log query CLI (cos errors / cos logs).
try:
    from cli.logs_commands import errors_cmd as _errors_cmd
    from cli.logs_commands import logs_cmd as _logs_cmd

    cli.add_command(_logs_cmd)
    cli.add_command(_errors_cmd)
except ImportError as _logs_cli_exc:  # pragma: no cover — defensive
    import logging as _logging

    _logging.getLogger("coding_os.cli").debug("logs CLI unavailable: %s", _logs_cli_exc)

# Doc lifecycle CLI (cos doc-new / doc-history / doc-lint).
try:
    from cli.doc_commands import doc_history_cmd as _doc_history_cmd
    from cli.doc_commands import doc_lint_cmd as _doc_lint_cmd
    from cli.doc_commands import doc_new_cmd as _doc_new_cmd

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
    marker = project / "src" / "core" / "thinking_os" / "server.py"
    cli_main = project / "src" / "cli" / "main.py"
    if marker.exists() and cli_main.exists():
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
def init(
    agent: str | None,
    template: tuple[str, ...],
    preset_id: str | None,
    dry_config: bool,
    extra_skills_csv: str | None,
    project_summary: str | None,
    project_dir: str | None,
    name: str | None,
    debug: bool,
    git: bool,
    force: bool,
    yes: bool,
    output_format: str,
    today_override: str | None,
    no_register: bool,
    do_index: bool,
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

    if dry_config:
        _dry_config_preview(template, output_format)
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

    # Non-TTY without --yes: refuse to guess targets silently (TASK-359).
    # Sits AFTER existing-install detection so the idempotent sync path keeps
    # working for a bare re-`cos init` inside a project.
    if not yes and not sys.stdin.isatty():
        if agent is None:
            click.echo(
                "ERROR: non-interactive shell — pass --agent (and --name/--project-dir), "
                "or use --yes.",
                err=True,
            )
            sys.exit(2)
        if name is None and project_dir is None and not debug:
            click.echo(
                "ERROR: non-interactive shell — pass --name and/or --project-dir "
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
        _run_scaffold_phase(
            agents,
            template,
            project,
            today=today_override,
            no_register=no_register,
            do_index=do_index,
            active_preset=active_preset,
            extra_skills=extra_skills,
            project_summary=project_summary,
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
    click.echo("\nQuick start:")
    click.echo("  cos daily              # Project status + today's tasks")
    click.echo("  cos task-pick          # See next recommended task")
    click.echo("  cos task-start TASK-001   # Start working")

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


def _run_scaffold_phase(
    agents: list[str],
    template: tuple[str, ...],
    project: Path,
    *,
    today: str | None = None,
    no_register: bool = False,
    do_index: bool = True,
    active_preset=None,
    extra_skills: list[str] | None = None,
    project_summary: str | None = None,
) -> None:
    """Original scaffolding body — extracted so it can be redirected in JSON mode.

    `today` is an optional ISO-8601 override for {{DATE}} substitution
    in scaffolded files (used by golden parity tests for determinism).

    `no_register` skips the global registry write (step 12). Sandbox
    fixtures (manifest-regen, golden parity tests) pass it so disposable
    temp dirs don't pollute ~/.coding-os/registry.json.
    """

    # 1. Create state directory
    state = project / STATE_DIR
    state.mkdir(parents=True, exist_ok=True)
    click.echo(f"  Created {STATE_DIR}/")
    stamp_core_version(state)

    # 2. Initialize DB directory
    db_path = state / "coding-os.db"
    if not db_path.exists():
        # Initialize the database
        brain_dir = str(CORE_DIR / "thinking_os")
        init_code = (
            "import sys; "
            f"sys.path.insert(0, {brain_dir!r}); "
            "from database import init_db; "
            f"init_db({str(db_path)!r})"
        )
        env = os.environ.copy()
        env["COS_DB_PATH"] = str(db_path)
        proc = subprocess.run(
            [sys.executable, "-c", init_code],
            env=env,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            click.echo("  ERROR: failed to initialize thinking_os database", err=True)
            if proc.stderr:
                click.echo(proc.stderr.strip(), err=True)
            click.echo(
                "  HINT: missing Python deps are the usual cause — run "
                "`uv sync --extra rag` in the coding-os checkout, then re-run `cos init` "
                "(machine prerequisites: `cos doctor --bootstrap`)",
                err=True,
            )
            raise SystemExit(1)
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
    if active_preset is not None:
        # Provenance + pass-through for later layers: extra-skill linking is
        # TASK-370, module toggle behavior is TASK-349.
        config["preset"] = active_preset.id
        if active_preset.skills:
            config["extra_skills"] = list(active_preset.skills)
        if active_preset.modules:
            config["modules"] = dict(active_preset.modules)
    if extra_skills:
        # --skills / wizard extras merge on top of preset-declared ones.
        config["extra_skills"] = list(
            dict.fromkeys([*(config.get("extra_skills") or []), *extra_skills])
        )
    _save_config(project, config)
    # Preset/wizard module toggles land in project state BEFORE the scaffold
    # copy so tag-driven docs composition sees them (TASK-360). Disable order:
    # dependents first (the registry refuses chains, e.g. docs before tasks).
    module_toggles = {k: v for k, v in (config.get("modules") or {}).items() if v is False}
    if module_toggles:
        from cli.subsystems import load_subsystems, set_module_enabled

        registry_modules = load_subsystems()

        def _dependents_being_disabled(module_id: str) -> int:
            # Dependents disable BEFORE their dependencies (the registry
            # refuses e.g. docs-off while tasks is still enabled).
            return sum(
                1
                for other in module_toggles
                if other in registry_modules
                and module_id in registry_modules[other].depends_on
            )

        ordered = sorted(module_toggles, key=_dependents_being_disabled)
        for module_id in ordered:
            toggle = set_module_enabled(project, module_id, False)
            if not toggle.ok:
                click.echo(f"  WARN: module '{module_id}': {toggle.reason}", err=True)
            else:
                click.echo(f"  Module disabled per preset: {module_id}")
    if project_summary and project_summary.strip():
        # Onboarding intake — consumed by the description→PRD pipeline (TASK-364).
        meta_dir = project / "docs" / "_meta"
        meta_dir.mkdir(parents=True, exist_ok=True)
        (meta_dir / "project-description.md").write_text(
            "# Project Description (onboarding intake)\n\n" + project_summary.strip() + "\n",
            encoding="utf-8",
        )
        click.echo("  Seeded docs/_meta/project-description.md")
        # Docs-module gate: preset/wizard module toggles are stored in config
        # (behavior SSOT lands with TASK-349); docs defaults ON.
        if (config.get("modules") or {}).get("docs", True):
            from cli.setup import seed_prd_from_text

            seeded = seed_prd_from_text(project, project_summary, date=today)
            if seeded:
                click.echo(f"  Seeded {len(seeded)} PRD doc(s): {', '.join(seeded)}")
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
    if project_summary and project_summary.strip():
        # The user's own words replace the generic default everywhere the
        # {{PROJECT_DESCRIPTION}} placeholder appears (TASK-364).
        substitutions = {
            **substitutions,
            "PROJECT_DESCRIPTION": " ".join(project_summary.split()),
        }

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

    # 7b. Compose .coding-os/ configs (rag/scrumban/domain) from base + every
    # installed stack — deep-merged, multi-stack-correct. The overlay (step 7)
    # deliberately skips these. SSOT: docs/engineering/config-composition.md.
    config_conflicts: list[str] = []
    composed = compose_coding_os_configs(
        project, state, list(template), templates_dir=TEMPLATES_DIR, conflicts=config_conflicts
    )
    if composed:
        click.echo(f"  Composed {len(composed)} .coding-os config(s): {', '.join(composed)}")
    for line in config_conflicts:
        click.echo(f"  WARN: config conflict (later wins) — {line}", err=True)

    # 8. Copy thinking_os reference doc from src/core/docs/
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

    # 9b. Aggregate scaffold-boundary.yaml from every installed stack so the
    # consumer-side enforce-scaffold-boundary.sh hook can enforce subtree
    # isolation at runtime. SSOT spec: docs/governance/scaffold-boundary-contract.md.
    _aggregate_scaffold_boundaries(project, state, template)

    # 10. Generate AGENTS.md by composing fragments from base + stacks.
    # No template file is read; the content is assembled by render_agents_md()
    # from the fragments registered in base.yaml::agents_md_sections (and any
    # fragments stacks contribute via their own stack.yaml::agents_md_sections).
    if ensure_agents_md(project, world):
        click.echo("  Generated AGENTS.md")

    # 11. Initial RAG indexing of the scaffolded docs so `cos_doc_search`
    # returns hits from the very first session. Without this, the
    # consumer's document_chunks table is empty until the user runs
    # `make docs-index` manually — Rule 19 (doc-sync) enforcement is
    # also effectively off until something hits the FTS index.
    # Skipped under --no-index: the index lives in the gitignored runtime DB,
    # so fast/CI/fixture scaffolds (e.g. golden capture) don't pay the
    # ~15s embedding-model load for output they discard.
    if do_index:
        _initial_doc_index(project, state)
    else:
        click.echo("  Skipped initial doc index (--no-index)")

    # 12. Register project in the global ~/.coding-os/registry.json so the
    # Hub web UI (`cos hub`) can enumerate it and serve its sqlite DB.
    # Skipped when --no-register passed (sandbox fixtures use disposable
    # temp dirs — registering them creates stale entries doctor then warns
    # about in hub.project_paths_exist).
    if no_register:
        click.echo("  Skipped hub registry write (--no-register)")
    else:
        try:
            from cli.registry import add_project as _registry_add_project

            entry = _registry_add_project(project)
            click.echo(f"  Registered in hub registry: {entry.slug}")
        except Exception as exc:
            # Registry is non-fatal — a failed write should not break init.
            click.echo(f"  WARN: could not register project in hub registry: {exc}", err=True)
            click.echo(
                "  HINT: register later with `cos registry add <project-path>` "
                "so the hub web UI can see this project",
                err=True,
            )


def _initial_doc_index(project: Path, state: Path) -> None:
    """Seed document_chunks + FTS for a freshly-scaffolded project."""
    rag_config = state / "rag-config.yaml"
    if not rag_config.exists():
        return
    db_path = state / "coding-os.db"
    brain_dir = str(CORE_DIR / "thinking_os")
    code = (
        "import sys; "
        f"sys.path.insert(0, {brain_dir!r}); "
        "from database import init_db; "
        "from doc_indexer import index_docs; "
        "from pathlib import Path; "
        f"conn = init_db({str(db_path)!r}); "
        f"stats = index_docs(conn, Path({str(rag_config)!r}), Path({str(project)!r})); "
        "conn.close(); "
        "print(f\"  Indexed {stats['updated_files']} doc(s), {stats['new_chunks']} chunk(s)\")"
    )
    env = os.environ.copy()
    env["COS_DB_PATH"] = str(db_path)
    result = subprocess.run(
        [sys.executable, "-c", code],
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0 and result.stdout.strip():
        click.echo(result.stdout.rstrip())
    elif result.returncode != 0:
        # Non-fatal: missing yaml / embeddings extras shouldn't break init.
        click.echo(
            f"  WARN: initial doc index skipped: {result.stderr.strip().splitlines()[-1] if result.stderr else 'unknown'}",
            err=True,
        )
        click.echo(
            "  HINT: doc search stays empty until indexed — install extras with "
            "`uv sync --extra rag` in the coding-os checkout, then run `make docs-index` here",
            err=True,
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
                    if ejected % 50 == 0:
                        click.echo(f"  … ejected {ejected} symlinks so far", err=True)

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
        ln
        for ln in lines
        if all(f in ln for f in filters) and (show_all or _is_decision_state(ln))
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
