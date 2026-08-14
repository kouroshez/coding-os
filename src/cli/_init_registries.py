"""Registry, path, and module-flag resolution for `cos init` and friends.

Leaf module: it reads the stack/adapter/profile registries and the subsystem
list and nothing else in cli.* imports back into it, so every other init module
can depend on it without a cycle. Rule 11 lives here — no stack or adapter
literal is hardcoded; every list is discovered from yaml.
"""

from __future__ import annotations

import contextlib
import functools
import sys
from pathlib import Path

import click
import yaml

from cli._resources import (
    adapters_dir,
    core_dir,
    overlay_adapter_dirs,
    overlay_template_dirs,
    templates_dir,
)
from cli.adapter_registry import load_adapter_registry
from cli.stack_registry import load_base_profile, load_stack_registry

CONFIG_FILE = ".coding-os.yaml"
STATE_DIR = ".coding-os"

ADAPTERS_DIR = adapters_dir()
CORE_DIR = core_dir()
TEMPLATES_DIR = templates_dir()

# Process-lifetime caches; _reset_registries_for_tests() clears them.
_base_cache = None
_stack_cache = None
_adapter_cache = None


def _discover_valid_agents() -> list[str]:
    """Read adapter ids from adapters/*/adapter.yaml at CLI startup.

    Deliberately separate from `_get_adapter_registry()` because click
    needs a plain list at decorator evaluation time, before module
    initialization has completed. Returns a conservative fallback on
    any load error so the CLI stays bootable.
    """
    try:
        return sorted(
            load_adapter_registry(ADAPTERS_DIR, overlay_dirs=overlay_adapter_dirs()).keys()
        )
    except Exception:
        return []


def _discover_valid_templates() -> list[str]:
    """Read stack ids from templates/*/stack.yaml (+ community overlay) at CLI startup."""
    try:
        return sorted(
            load_stack_registry(TEMPLATES_DIR, overlay_dirs=overlay_template_dirs()).keys()
        )
    except Exception:
        return []


def _get_base_profile():
    global _base_cache
    if _base_cache is None:
        _base_cache = load_base_profile(TEMPLATES_DIR / "_base")
    return _base_cache


def _get_stack_registry():
    global _stack_cache
    if _stack_cache is None:
        # Consumer-discovery path: include out-of-tree community stacks
        # ($COS_USER_TEMPLATES_DIR). The meta-repo SSOT regen/lint scripts load
        # the registry bundled-only (no overlay) so a community stack never leaks
        # into scaffold_manifest.json / dimension-registry.md.
        _stack_cache = load_stack_registry(TEMPLATES_DIR, overlay_dirs=overlay_template_dirs())
    return _stack_cache


def _get_adapter_registry():
    global _adapter_cache
    if _adapter_cache is None:
        _adapter_cache = load_adapter_registry(ADAPTERS_DIR, overlay_dirs=overlay_adapter_dirs())
    return _adapter_cache


def _reset_registries_for_tests() -> None:
    """Clear cached registry state. Call from test fixtures that mutate
    templates/ or adapters/ between invocations within a single process."""
    global _base_cache, _stack_cache, _adapter_cache
    _base_cache = None
    _stack_cache = None
    _adapter_cache = None


def _example_swimlane(project: Path) -> str:
    # Swimlane ids are per-stack (angular: components…, wordpress: theme…), so a
    # literal in the quick-start example would fail validation in most projects —
    # read the set this project actually composed.
    with contextlib.suppress(Exception):
        raw = (project / STATE_DIR / "scrumban-config.yaml").read_text(encoding="utf-8")
        return str((yaml.safe_load(raw) or {})["swimlanes"][0]["id"])
    return "<swimlane>"


def _registered_slug(project: Path) -> str:
    # The hub slug the Composer navigates by; "" under --no-register or a failed
    # registry write, both of which are non-fatal for init itself.
    import logging

    try:
        from cli.registry import load_registry

        # add_project matches on the unresolved path, so match both forms —
        # resolving only would miss a symlinked entry it had just written.
        wanted = {str(project), str(project.resolve())}
        for entry in load_registry().projects:
            stored = Path(entry.path)
            if str(stored) in wanted or str(stored.resolve()) in wanted:
                return entry.slug
    except Exception as exc:
        logging.getLogger(__name__).debug("slug lookup skipped: %s", exc)
    return ""


@functools.lru_cache(maxsize=1)
def _subsystem_help_lists() -> tuple[str, str]:
    # Rule 11 — the ids come from subsystems.yaml, never a literal that rots as
    # modules are added (hidden ones are not user-selectable, so they stay out).
    # Cached: these run at decoration time on every `cos` invocation, and both
    # init and adopt declare the flags, so an uncached read costs 4 yaml loads.
    fallback = "see src/core/subsystems.yaml"
    try:
        from cli.subsystems import load_profiles, load_subsystems

        ids = [m.id for m in load_subsystems().values() if not m.kernel and not m.hidden]
        profiles, default_profile = load_profiles()
    except Exception:
        return fallback, fallback
    return (
        ", ".join(ids) or fallback,
        ", ".join(f"{n} (default)" if n == default_profile else n for n in profiles) or fallback,
    )


def _module_flag_help() -> str:
    return (
        f"Subsystem module to disable at create (repeatable): {_subsystem_help_lists()[0]}. "
        "kernel can't be disabled; modules that depend on it are disabled with it. "
        "Wizard parity with the Composer module toggles."
    )


def _profile_flag_help() -> str:
    return (
        f"Module profile curating the agent's MCP tool surface: {_subsystem_help_lists()[1]}. "
        "UNIONED with --disable-module (a profile can only remove modules, never "
        "re-add one — use --enable-module to keep one on); omit to use the "
        "registry default."
    )


def _enable_flag_help() -> str:
    return (
        "Force-enable a module after the profile union (repeatable) — the escape "
        "from profile+--disable-module union semantics, which can only remove. "
        "Pulls the module's depends_on chain in with it; combining with "
        "--disable-module of the same id is an error."
    )


def _validated_disabled_modules(disable_module: tuple[str, ...]) -> list[str]:
    # Validate --disable-module up-front so BOTH the dry-run preview and the real
    # init reject the same ids (pass-3 review: dry-run returned before validation,
    # so a typo'd module gave a false all-clear). kernel ids are non-disableable.
    if not disable_module:
        return []
    from cli.subsystems import close_over_dependents, load_subsystems

    registry_modules = load_subsystems()
    disabled = list(dict.fromkeys(m.strip() for m in disable_module if m.strip()))
    unknown = [m for m in disabled if m not in registry_modules]
    if unknown:
        click.echo(
            f"ERROR: unknown module(s) {unknown} — available: {sorted(registry_modules)}.",
            err=True,
        )
        sys.exit(2)
    kernel = [m for m in disabled if registry_modules[m].kernel]
    if kernel:
        click.echo(f"ERROR: module(s) {kernel} are kernel and cannot be disabled.", err=True)
        sys.exit(2)
    closed = close_over_dependents(disabled, registry_modules)
    added = [m for m in closed if m not in disabled]
    if added:
        # stderr: this runs before the json-mode stdout redirect, and a progress
        # line on stdout makes `cos init --format json | jq` a parse error.
        click.echo(f"  Also disabling dependent module(s): {', '.join(sorted(added))}", err=True)
    return closed


def _apply_enable_modules(
    disabled: list[str],
    enable_module: tuple[str, ...],
    explicit_disable: tuple[str, ...],
) -> list[str]:
    # The escape from union semantics: --enable-module wins over a profile's
    # disable, but contradicting an explicit --disable-module is an error, not
    # a merge. Dependencies come along so the final set stays closed.
    if not enable_module:
        return disabled
    from cli.subsystems import load_subsystems

    registry_modules = load_subsystems()
    enabled = list(dict.fromkeys(m.strip() for m in enable_module if m.strip()))
    unknown = [m for m in enabled if m not in registry_modules]
    if unknown:
        click.echo(
            f"ERROR: unknown module(s) {unknown} — available: {sorted(registry_modules)}.",
            err=True,
        )
        sys.exit(2)
    conflict = sorted(set(enabled) & {m.strip() for m in explicit_disable if m.strip()})
    if conflict:
        click.echo(
            f"ERROR: module(s) {conflict} passed to both --enable-module and --disable-module.",
            err=True,
        )
        sys.exit(2)
    keep: set[str] = set()
    frontier = list(enabled)
    while frontier:
        module_id = frontier.pop()
        if module_id in keep:
            continue
        keep.add(module_id)
        frontier.extend(d for d in registry_modules[module_id].depends_on if d in registry_modules)
    re_enabled = sorted(set(disabled) & keep)
    if re_enabled:
        click.echo(f"  Re-enabling module(s): {', '.join(re_enabled)}", err=True)
    return [m for m in disabled if m not in keep]


VALID_AGENTS: list[str] = _discover_valid_agents()
