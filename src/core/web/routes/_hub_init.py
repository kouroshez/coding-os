"""Init input validation and argv construction for the create-from-UI flow.

Pure functions: they decide whether a scaffold request is legal and what `cos
init` argv expresses it. Running the subprocess is the routes module's job, so
this file stays testable without a filesystem.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import sys
import uuid
from pathlib import Path

from fastapi.responses import JSONResponse

from ._hub_shared import (
    _PROJECT_NAME_RE,
    _ancestor_with_coding_os,
    _err,
    _is_meta_repo,
)

logger = logging.getLogger("coding_os.web.hub")


def _cos_init_command() -> list[str]:
    """Resolve how to invoke `cos` — the installed bin, else `python -m cli.main`."""
    found = shutil.which("cos")
    return [found] if found else [sys.executable, "-m", "cli.main"]


def _resolve_agents(agent: str, agents: list[str] | None) -> list[str]:
    """Merge the single `agent` (back-compat) + `agents` list into a deduped,
    order-preserving list; defaults to ['claude'] when both are empty.

    A project may legitimately host several adapters (.claude/ + .codex/) —
    the CLI already supports `--agent claude,codex` (main.py::_parse_agents)."""
    merged: list[str] = []
    for candidate in [*(agents or []), agent]:
        token = (candidate or "").strip()
        if token and token not in merged:
            merged.append(token)
    return merged or ["claude"]


def _validate_init_inputs(
    name: str,
    parent_dir: str,
    stacks: list[str],
    preset: str,
    agents: list[str],
    extra_skills: list[str] | None = None,
    disabled_modules: list[str] | None = None,
) -> tuple[JSONResponse | dict | None, dict]:
    """Shared dry-run validation for validate-init AND registry/init (SSOT).

    Returns (error_response, info). info carries name/auto_named/parent/
    target/templates once every check passes. No filesystem writes."""
    info: dict = {}
    name = (name or "").strip()
    if name:
        if not _PROJECT_NAME_RE.match(name):
            return (
                _err(
                    "validation",
                    "name must match ^[a-z0-9][a-z0-9._-]{0,63}$ (lowercase, no spaces)",
                ),
                {},
            )
        info["name"], info["auto_named"] = name, False
    else:
        # "don't know yet" — temp slug, renameable later via registry rename.
        info["name"], info["auto_named"] = f"proj-{uuid.uuid4().hex[:6]}", True

    if not isinstance(parent_dir, str) or not parent_dir.strip():
        return _err("validation", "parent_dir is required"), {}
    try:
        parent = Path(parent_dir).expanduser().resolve()
    except (OSError, RuntimeError) as exc:
        return _err("validation", f"invalid parent_dir: {exc}"), {}
    if not parent.is_dir():
        return _err("not_found", f"parent_dir is not a directory: {parent}", status=404), {}
    if not os.access(parent, os.W_OK):
        return _err("validation", f"parent_dir is not writable: {parent}"), {}
    if _is_meta_repo(parent):
        return _err("validation", "cannot scaffold inside the coding-os meta-repo checkout"), {}
    target = parent / info["name"]
    if target.exists():
        return _err("conflict", f"{target} already exists", status=409), {}
    nested = _ancestor_with_coding_os(parent)
    if nested is not None:
        return (
            _err(
                "validation",
                f"{parent} is inside the registered project {nested} — pick a parent outside it",
            ),
            {},
        )

    try:
        from cli.list_stacks import TEMPLATES_DIR  # type: ignore
        from cli.stack_registry import load_stack_registry  # type: ignore

        stack_reg = load_stack_registry(TEMPLATES_DIR)
    except Exception as exc:
        return _err("unavailable", f"stack registry unavailable: {exc}", status=503), {}
    stacks = [s for s in (stacks or []) if s]
    unknown = [s for s in stacks if s not in stack_reg]
    if unknown:
        return _err("validation", f"unknown stack(s): {unknown}"), {}
    if preset:
        if stacks:
            return _err("validation", "preset and stacks are mutually exclusive"), {}
        from cli.preset_registry import load_preset_registry  # type: ignore

        presets = load_preset_registry(TEMPLATES_DIR, known_stacks=set(stack_reg.keys()))
        if preset not in presets:
            return _err("not_found", f"preset '{preset}' not found", status=404), {}
        info["templates"] = list(presets[preset].stacks)
    else:
        info["templates"] = stacks

    try:
        from cli._resources import adapters_dir  # type: ignore
        from cli.adapter_registry import load_adapter_registry  # type: ignore

        adapter_reg = load_adapter_registry(adapters_dir())
    except Exception as exc:
        return _err("unavailable", f"adapter registry unavailable: {exc}", status=503), {}
    if not agents:
        return _err("validation", "at least one agent is required"), {}
    unknown_agents = [a for a in agents if a not in adapter_reg]
    if unknown_agents:
        return (
            _err(
                "validation",
                f"unknown agent(s) {unknown_agents} — available: {sorted(adapter_reg)}",
            ),
            {},
        )
    info["agents"] = list(agents)

    # Module toggles: validate against the subsystem registry —
    # kernel is non-disableable, and the set is closed over dependents before
    # it reaches init: the scaffold REFUSES (never cascades) an unclosed one,
    # so an unclosed set would return ok for a project contradicting the request.
    disabled_modules = [m for m in (disabled_modules or []) if m]
    if disabled_modules:
        try:
            from cli.subsystems import load_subsystems  # type: ignore

            registry_modules = load_subsystems()
        except Exception as exc:
            return _err("unavailable", f"subsystem registry unavailable: {exc}", status=503), {}
        unknown_mods = [m for m in disabled_modules if m not in registry_modules]
        if unknown_mods:
            return _err("validation", f"unknown module(s): {unknown_mods}"), {}
        kernel_mods = [m for m in disabled_modules if registry_modules[m].kernel]
        if kernel_mods:
            return _err(
                "validation", f"module(s) {kernel_mods} are kernel and cannot be disabled"
            ), {}
        # Same closure the CLI applies, so an identical payload produces an
        # identical project through either entrypoint.
        try:
            from cli.subsystems import close_over_dependents  # type: ignore

            disabled_modules = close_over_dependents(disabled_modules, registry_modules)
        except Exception as exc:
            return _err("unavailable", f"subsystem registry unavailable: {exc}", status=503), {}
    info["disabled_modules"] = disabled_modules

    # Argv allowlist: every value that reaches the subprocess argv
    # is validated against a registry — skills included.
    if extra_skills:
        try:
            from cli.skill_registry import load_skill_registry  # type: ignore
            from cli.skills_list import CORE_SKILLS_DIR  # type: ignore

            known_skills = set(load_skill_registry(CORE_SKILLS_DIR).skills.keys())
        except Exception as exc:
            return _err("unavailable", f"skill registry unavailable: {exc}", status=503), {}
        unknown_skills = [s for s in extra_skills if s not in known_skills]
        if unknown_skills:
            return _err("validation", f"unknown skill(s): {unknown_skills}"), {}

    info["parent"], info["target"] = parent, target
    return None, info


def _default_profile_reenables(disabled_modules: list[str]) -> list[str]:
    # Modules the chips kept ON that the default profile would disable —
    # emitted as --enable-module so the payload stays authoritative without
    # pinning a profile. Hidden modules follow the profile: the chips never
    # show them, so the caller expressed no intent about them.
    try:
        from cli.subsystems import load_profiles, load_subsystems, resolve_profile  # type: ignore

        modules = load_subsystems()
        _, default_name = load_profiles()
        default_disabled = resolve_profile(default_name)
    except Exception as exc:
        logger.debug("profile lookup failed: %s", exc)
        return []
    off = set(disabled_modules)
    return sorted(
        module_id
        for module_id in default_disabled
        if module_id not in off and module_id in modules and not modules[module_id].hidden
    )


def _build_cos_init_cmd(
    name: str,
    parent_dir: str,
    stacks: list[str],
    agents: list[str],
    preset: str = "",
    description: str = "",
    extra_skills: list[str] | None = None,
    disabled_modules: list[str] | None = None,
) -> list[str]:
    """One argv builder for sync AND job-based init (parity stays in the CLI)."""
    cmd = [
        *_cos_init_command(),
        "init",
        "--name",
        name,
        "--project-dir",
        parent_dir,
        "--agent",
        ",".join(agents),
        "--yes",
        "--no-index",
        # Skip the heavy doc-RAG embedding but still build the knowledge graph
        # (AST walk, no model) so the new project's Graph tab is never empty.
        "--graph-index",
        "--format",
        "json",
    ]
    if disabled_modules:
        # init UNIONS the profile's disabled set with --disable-module, so the
        # chips a user left ON must ride as --enable-module or the default
        # profile silently turns them off. With no explicit set, stay silent so
        # a bare API create matches a hand-typed `cos init`.
        for module_id in _default_profile_reenables(disabled_modules):
            cmd += ["--enable-module", module_id]
    if preset:
        cmd += ["--preset", preset]
    for stack in stacks:
        cmd += ["--template", stack]
    if description.strip():
        cmd += ["--summary", description.strip()]
    if extra_skills:
        cmd += ["--skills", ",".join(extra_skills)]
    for module_id in disabled_modules or []:
        cmd += ["--disable-module", module_id]
    return cmd


def _parse_init_payload(stdout_lines: list[str]) -> dict:
    # init pretty-prints the summary, and the job runner merges stderr progress
    # into the same pipe, so the object can be preceded AND followed by noise.
    # raw_decode stops at the end of the first complete value.
    text = "\n".join(stdout_lines)
    decoder = json.JSONDecoder()
    start = text.find("{")
    while start != -1:
        try:
            parsed, _ = decoder.raw_decode(text[start:])
        except json.JSONDecodeError:
            start = text.find("{", start + 1)
            continue
        if isinstance(parsed, dict):
            return parsed
        start = text.find("{", start + 1)
    return {}
