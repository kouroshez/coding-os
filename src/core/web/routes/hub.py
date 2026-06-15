"""core.web.routes.hub — global Hub registry endpoints."""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Body, Query
from fastapi.responses import JSONResponse

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

logger = logging.getLogger("coding_os.web.hub")
router = APIRouter(prefix="/api/hub", tags=["hub"])


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _looks_like_cos_project(path: Path) -> bool:
    """Quick heuristic: directory exists and has .coding-os/ inside."""
    try:
        return path.is_dir() and (path / ".coding-os").is_dir()
    except OSError:
        return False


def _is_hub_state_dir(coding_os: Path) -> bool:
    """True when this .coding-os/ is the GLOBAL hub state dir, not a project's.

    The global ~/.coding-os/ carries the hub registry + pid; a project's
    .coding-os/ never does (hub-architecture.md § address spaces). Lets the
    home/global dir be rejected as a phantom "runtime-cwd" project.
    """
    try:
        return (coding_os / "registry.json").is_file() or (coding_os / "hub.pid").is_file()
    except OSError:
        return False


def _is_meta_repo(path: Path) -> bool:
    """True when `path` is the coding-os meta-repo checkout itself.

    Recognises the dogfood case: the meta-repo lives at
    `<somewhere>/coding-os/` AND ships its own `.coding-os/`
    (dogfood — Principle P5). It must never be flagged as "nested
    inside another coding-os project" just because a higher-up
    ancestor (e.g. `~/.coding-os/` scratch dir) happens to have a
    `.coding-os/`.
    """
    try:
        return (
            (path / "src" / "cli" / "main.py").is_file()
            and (path / "src" / "core" / "thinking_os" / "server.py").is_file()
            and (path / "pyproject.toml").is_file()
        )
    except OSError:
        return False


def _is_registered_project(path: Path) -> bool:
    """True iff `path` (resolved) is recorded in the cli registry.

    The nested-project check should only fire when the enclosing
    ancestor is an *actual registered project*. A stray
    `~/.coding-os/` (left over from a test run, or the user's
    scratch dir) is not a project — blocking on it has rejected
    legitimate contributor checkouts (issue reported 2026-05-23).
    """
    try:
        from cli.registry import load_registry  # type: ignore

        reg = load_registry()
    except Exception:
        return False
    target = str(path.resolve())
    for p in reg.projects:
        try:
            if str(Path(p.path).resolve()) == target:
                return True
        except (OSError, RuntimeError):
            continue
    return False


def _ancestor_with_coding_os(path: Path) -> Path | None:
    """Walk parents looking for an enclosing **registered** coding-os
    project root.

    Returns the first ancestor (strictly above `path`) that has a
    `.coding-os/` directory AND is recorded in the cli registry —
    a true nesting violation. An ancestor with just `.coding-os/`
    on disk but not in the registry is treated as noise (scratch,
    leftover) and ignored.

    Also skips the check entirely when `path` is the meta-repo
    itself (dogfood — see `_is_meta_repo`).
    """
    try:
        resolved = path.resolve()
    except (OSError, RuntimeError):
        return None
    if _is_meta_repo(resolved):
        return None
    for parent in resolved.parents:
        try:
            if (parent / ".coding-os").is_dir() and _is_registered_project(parent):
                return parent
        except OSError:
            continue
    return None


def _resolve_slug_from_registry(cwd: Path) -> str:
    """Match cli.registry._derive_slug so UI and API agree on spelling."""
    try:
        from cli.registry import _derive_slug  # type: ignore

        return _derive_slug(cwd)
    except Exception as exc:
        logger.debug("cli.registry._derive_slug unavailable: %s", exc)
        return cwd.name.lower().strip() or "project"


def _derive_runtime_entry() -> dict | None:
    """Return an in-memory entry for the cwd project when it's a cos repo."""
    cwd = Path(os.environ.get("COS_PROJECT_ROOT") or os.getcwd()).resolve()
    # $HOME hosts the GLOBAL hub state at ~/.coding-os/ — never a project.
    try:
        if cwd == Path.home().resolve():
            return None
    except (OSError, RuntimeError):
        pass
    if not _looks_like_cos_project(cwd):
        return None
    # A .coding-os/ carrying the hub registry/pid is the global state dir,
    # not a project root (e.g. the Hub booted from a non-home COS_HOME).
    if _is_hub_state_dir(cwd / ".coding-os"):
        return None
    # .coding-os/ only exists at the project root.  A nested .coding-os/
    # inside another project (e.g. src/core/web/ui/.coding-os/ left over
    # from a test run) must NEVER surface as a separate project entry —
    # we'd hijack the Hub's "default" slot with a stray dir.
    if _ancestor_with_coding_os(cwd) is not None:
        return None
    return {
        "slug": _resolve_slug_from_registry(cwd),
        "path": str(cwd),
        "created_at": "",
        "source": "runtime-cwd",
    }


def _err(category: str, message: str, *, status: int = 400) -> JSONResponse:
    """Shared error-envelope shape matching the rest of /api/*."""
    return JSONResponse(
        status_code=status,
        content={
            "error": {
                "category": category,
                "retryable": False,
                "message": message,
            },
        },
    )


def _validate_project_path(raw: str) -> tuple[Path | None, JSONResponse | None]:
    """Sanitize an incoming project-path string for registry mutations."""
    if not isinstance(raw, str) or not raw.strip():
        return None, _err("validation", "path is required and must be a non-empty string")
    try:
        path = Path(raw).expanduser().resolve()
    except (OSError, RuntimeError) as exc:
        return None, _err("validation", f"invalid path: {exc}")
    if not path.is_dir():
        return None, _err("not_found", f"path is not a directory: {path}", status=404)
    if not _looks_like_cos_project(path):
        return None, _err(
            "validation",
            f"{path} has no .coding-os/ — run `cos init` there first",
        )
    ancestor = _ancestor_with_coding_os(path)
    if ancestor is not None:
        return None, _err(
            "validation",
            (
                f"{path} sits inside {ancestor} which is already a coding-os "
                "project — .coding-os/ must only exist at the project root. "
                "Remove the nested .coding-os/ directory."
            ),
        )
    return path, None


# ---------------------------------------------------------------------------
# GET /api/hub/projects
# ---------------------------------------------------------------------------


@router.get("/projects")
def hub_projects() -> dict:
    """List every registered coding-os project whose directory still exists."""
    projects: list[dict] = []
    seen_paths: set[str] = set()
    try:
        from cli.registry import load_registry  # type: ignore

        reg = load_registry()
    except Exception as exc:
        logger.debug("load_registry failed: %s", exc)
        reg = None

    if reg is not None:
        for p in reg.projects:
            path = Path(p.path)
            if not _looks_like_cos_project(path):
                continue
            resolved = str(path.resolve())
            if resolved in seen_paths:
                continue
            seen_paths.add(resolved)
            projects.append(
                {
                    "slug": p.slug,
                    "path": p.path,
                    "created_at": p.created_at,
                    "source": "registry",
                }
            )

    runtime = _derive_runtime_entry()
    if runtime is not None:
        resolved = str(Path(runtime["path"]).resolve())
        if resolved not in seen_paths:
            projects.insert(0, runtime)

    return {"projects": projects, "count": len(projects)}


# ---------------------------------------------------------------------------
# POST /api/hub/registry/add
# ---------------------------------------------------------------------------


@router.post("/registry/add")
def hub_registry_add(
    path: str = Body(..., embed=True),
    slug: str | None = Body(None, embed=True),
):
    """Register an existing `.coding-os/` directory with the Hub."""
    resolved, err = _validate_project_path(path)
    if err is not None:
        return err
    if slug is not None and not isinstance(slug, str):
        return _err("validation", "slug must be a string when provided")

    try:
        from cli.registry import add_project  # type: ignore
    except Exception as exc:
        return _err(
            "unavailable",
            f"cli.registry unavailable: {exc}",
            status=503,
        )

    try:
        entry = add_project(resolved, slug=(slug or "").strip() or None)
    except Exception as exc:
        return _err("validation", str(exc))

    return {
        "data": {
            "slug": entry.slug,
            "path": entry.path,
            "created_at": entry.created_at,
        },
        "meta": {"layer": "hub", "source": "hub.registry_add"},
    }


# ---------------------------------------------------------------------------
# GET /api/hub/stacks  +  POST /api/hub/registry/init (create-from-UI, TASK-249)
# ---------------------------------------------------------------------------

_PROJECT_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")


@router.get("/stacks")
def hub_stacks() -> dict:
    """List installable stack templates (data-driven from src/templates/*/stack.yaml)."""
    try:
        from cli.list_stacks import TEMPLATES_DIR  # type: ignore
        from cli.stack_registry import load_stack_registry  # type: ignore

        reg = load_stack_registry(TEMPLATES_DIR)
    except Exception as exc:
        return _err("unavailable", f"stack registry unavailable: {exc}", status=503)
    stacks = [
        {"id": s.id, "label": s.label, "category": s.category, "language": s.language}
        for s in sorted(reg.values(), key=lambda p: p.id)
        if s.id != "_base"
    ]
    return {
        "data": {"stacks": stacks, "count": len(stacks)},
        "meta": {"layer": "hub", "source": "hub.stacks"},
    }


@router.get("/adapters")
def hub_adapters() -> dict:
    """List installable agent adapters (data-driven from src/adapters/*/adapter.yaml)."""
    try:
        from cli._resources import adapters_dir  # type: ignore
        from cli.adapter_registry import load_adapter_registry  # type: ignore

        reg = load_adapter_registry(adapters_dir())
    except Exception as exc:
        return _err("unavailable", f"adapter registry unavailable: {exc}", status=503)
    adapters = [
        {"id": a.id, "label": a.label} for a in sorted(reg.values(), key=lambda a: a.id)
    ]
    return {
        "data": {"adapters": adapters, "count": len(adapters)},
        "meta": {"layer": "hub", "source": "hub.adapters"},
    }


@router.get("/modules")
def hub_modules() -> dict:
    """List subsystem modules (data-driven from src/core/subsystems.yaml) for the Composer."""
    try:
        from cli.subsystems import load_subsystems  # type: ignore

        registry = load_subsystems()
    except Exception as exc:
        return _err("unavailable", f"subsystem registry unavailable: {exc}", status=503)
    modules = [
        {
            "id": m.id,
            "label": m.label,
            "kernel": m.kernel,
            "depends_on": list(m.depends_on),
        }
        for m in registry.values()
    ]
    return {
        "data": {"modules": modules, "count": len(modules)},
        "meta": {"layer": "hub", "source": "hub.modules"},
    }


@router.get("/presets")
def hub_presets() -> dict:
    """List project presets (data-driven from src/templates/_presets/*.yaml)."""
    try:
        from cli.list_stacks import TEMPLATES_DIR  # type: ignore
        from cli.preset_registry import load_preset_registry  # type: ignore
        from cli.stack_registry import load_stack_registry  # type: ignore

        known = set(load_stack_registry(TEMPLATES_DIR).keys())
        registry = load_preset_registry(TEMPLATES_DIR, known_stacks=known)
    except Exception as exc:
        return _err("unavailable", f"preset registry unavailable: {exc}", status=503)
    presets = [
        {
            "id": p.id,
            "label": p.label,
            "description": p.description,
            "stacks": list(p.stacks),
        }
        for p in sorted(registry.values(), key=lambda p: p.id)
    ]
    return {
        "data": {"presets": presets, "count": len(presets)},
        "meta": {"layer": "hub", "source": "hub.presets"},
    }


@router.get("/skills")
def hub_skills() -> dict:
    """Global core+stack skill catalog with provenance + validation status."""
    try:
        from cli.skills_list import collect_skill_catalog  # type: ignore

        catalog = collect_skill_catalog()
    except Exception as exc:
        return _err("unavailable", f"skill catalog unavailable: {exc}", status=503)
    return {"data": catalog, "meta": {"layer": "hub", "source": "hub.skills"}}


@router.get("/stacks/{stack_id}/skills")
def hub_stack_skills(stack_id: str) -> dict:
    """Required/recommended/optional skill groups for one stack (onboarding preview)."""
    try:
        from cli.skills_list import collect_stack_skill_groups  # type: ignore

        payload = collect_stack_skill_groups(stack_id)
    except KeyError:
        return _err("not_found", f"stack '{stack_id}' not found", status=404)
    except Exception as exc:
        return _err("unavailable", f"skill groups unavailable: {exc}", status=503)
    return {"data": payload, "meta": {"layer": "hub", "source": "hub.stack_skills"}}


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

    # Module toggles (TASK-421): validate against the subsystem registry —
    # kernel is non-disableable; dependency-order disabling is handled at
    # scaffold time (set_module_enabled refuses invalid chains).
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
            return _err("validation", f"module(s) {kernel_mods} are kernel and cannot be disabled"), {}
    info["disabled_modules"] = disabled_modules

    # Argv allowlist (TASK-363): every value that reaches the subprocess argv
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


@router.post("/registry/validate-init")
def hub_registry_validate_init(
    name: str = Body("", embed=True),
    parent_dir: str = Body(..., embed=True),
    stacks: list[str] = Body(default_factory=list, embed=True),
    preset: str = Body("", embed=True),
    agent: str = Body("", embed=True),
    agents: list[str] = Body(default_factory=list, embed=True),
    extra_skills: list[str] = Body(default_factory=list, embed=True),
    disabled_modules: list[str] = Body(default_factory=list, embed=True),
):
    """Dry-run validation + merged-config preview for the onboarding wizard (TASK-358)."""
    resolved_agents = _resolve_agents(agent, agents)
    error, info = _validate_init_inputs(
        name, parent_dir, stacks, preset, resolved_agents,
        extra_skills=extra_skills, disabled_modules=disabled_modules,
    )
    if error is not None:
        return error
    swimlanes: list[str] = []
    conflicts: list[str] = []
    try:
        from cli.config_composer import preview_coding_os_configs  # type: ignore
        from cli.list_stacks import TEMPLATES_DIR  # type: ignore

        merged, conflicts = preview_coding_os_configs(
            info["templates"], templates_dir=TEMPLATES_DIR
        )
        scrumban = merged.get("scrumban-config.yaml") or {}
        swimlanes = [
            lane.get("id") for lane in scrumban.get("swimlanes") or [] if isinstance(lane, dict)
        ]
    except Exception as exc:
        logger.debug("dry-config preview failed: %s", exc)
    return {
        "data": {
            "valid": True,
            "name": info["name"],
            "auto_named": info["auto_named"],
            "target": str(info["target"]),
            "templates": info["templates"],
            "agents": info["agents"],
            "disabled_modules": info["disabled_modules"],
            "swimlanes": swimlanes,
            "conflicts": conflicts,
        },
        "meta": {"layer": "hub", "source": "hub.registry_validate_init"},
    }


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
    cmd = _cos_init_command() + [
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


def _run_cos_init(
    name: str,
    parent_dir: str,
    stacks: list[str],
    agents: list[str],
    preset: str = "",
    description: str = "",
    extra_skills: list[str] | None = None,
    disabled_modules: list[str] | None = None,
    timeout: int = 300,
):
    """Run `cos init` in a subprocess → (ok, payload, error).

    Default timeout has headroom over the in-init graph-build cap
    (COS_INIT_GRAPH_TIMEOUT, default 180s) so a slow graph build degrades to an
    empty graph inside init rather than the create subprocess being killed.

    Module-level so a test can monkeypatch it without a real scaffold.
    Description/extra-skills ride the CLI flags (--summary/--skills) so the
    wizard and a hand-typed `cos init` produce byte-identical projects."""
    cmd = _build_cos_init_cmd(
        name,
        parent_dir,
        stacks,
        agents,
        preset=preset,
        description=description,
        extra_skills=extra_skills,
        disabled_modules=disabled_modules,
    )
    try:
        proc = subprocess.run(  # noqa: S603 — fixed argv list, never shell=True
            cmd, capture_output=True, text=True, timeout=timeout, cwd=parent_dir
        )
    except subprocess.TimeoutExpired:
        return False, None, f"init timed out after {timeout}s"
    except OSError as exc:
        return False, None, f"could not launch cos init: {exc}"
    if proc.returncode != 0:
        return False, None, (proc.stderr or proc.stdout or "init failed").strip()[-400:]
    payload: dict = {}
    for line in reversed((proc.stdout or "").strip().splitlines()):
        candidate = line.strip()
        if candidate.startswith("{"):
            try:
                payload = json.loads(candidate)
                break
            except json.JSONDecodeError:
                continue
    return True, payload, ""


def _parse_init_payload(stdout_lines: list[str]) -> dict:
    """Last JSON object in init's stdout (init --format json emits it on success)."""
    for line in reversed(stdout_lines):
        candidate = line.strip()
        if candidate.startswith("{"):
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                continue
    return {}


@router.post("/registry/init")
def hub_registry_init(
    name: str = Body("", embed=True),
    parent_dir: str = Body(..., embed=True),
    stack: str = Body("", embed=True),
    stacks: list[str] = Body(default_factory=list, embed=True),
    preset: str = Body("", embed=True),
    agent: str = Body("", embed=True),
    agents: list[str] = Body(default_factory=list, embed=True),
    description: str = Body("", embed=True),
    extra_skills: list[str] = Body(default_factory=list, embed=True),
    disabled_modules: list[str] = Body(default_factory=list, embed=True),
    background: bool = Body(False, embed=True),
):
    """Scaffold a NEW project via `cos init` and register it (security-gated, TASK-249/358/362)."""
    all_stacks = [s for s in ((stacks or []) + ([stack] if stack else [])) if s]
    resolved_agents = _resolve_agents(agent, agents)
    error, info = _validate_init_inputs(
        name, parent_dir, all_stacks, preset, resolved_agents,
        extra_skills=extra_skills, disabled_modules=disabled_modules,
    )
    if error is not None:
        return error
    target: Path = info["target"]
    if background:
        # Job-based create (TASK-362): returns a job_id immediately; phases +
        # log stream over GET /api/hub/init-jobs/{id}/events.
        from web import init_jobs  # type: ignore

        cmd = _build_cos_init_cmd(
            info["name"],
            str(info["parent"]),
            all_stacks,
            resolved_agents,
            preset=preset,
            description=description or "",
            extra_skills=extra_skills or [],
            disabled_modules=info["disabled_modules"],
        )
        job = init_jobs.start_job(cmd, target, str(info["parent"]), _parse_init_payload)
        return {
            "data": {
                "job_id": job.job_id,
                "name": info["name"],
                "auto_named": info["auto_named"],
                "target": str(target),
            },
            "meta": {"layer": "hub", "source": "hub.registry_init_job"},
        }
    ok, payload, err = _run_cos_init(
        info["name"],
        str(info["parent"]),
        all_stacks,
        resolved_agents,
        preset=preset,
        description=description or "",
        extra_skills=extra_skills or [],
        disabled_modules=info["disabled_modules"],
    )
    if not ok:
        # A failed init must leave nothing — remove the partial scaffold.
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
        return _err("internal", f"init failed: {err}", status=500)
    slug = (payload or {}).get("slug") or _resolve_slug_from_registry(target)
    return {
        "data": {
            "slug": slug,
            "path": str(target),
            "stack": (all_stacks[0] if all_stacks else None),
            "stacks": all_stacks,
            "agents": resolved_agents,
            "disabled_modules": info["disabled_modules"],
            "preset": preset or None,
            "auto_named": info["auto_named"],
        },
        "meta": {"layer": "hub", "source": "hub.registry_init"},
    }


@router.get("/init-jobs/{job_id}")
def hub_init_job_snapshot(job_id: str):
    """Current phase + status + log tail for a tracked init job (TASK-362)."""
    from web import init_jobs  # type: ignore

    job = init_jobs.get_job(job_id)
    if job is None:
        return _err("not_found", f"no init job {job_id!r}", status=404)
    return {"data": job.snapshot(), "meta": {"layer": "hub", "source": "hub.init_job"}}


@router.post("/init-jobs/{job_id}/cancel")
def hub_init_job_cancel(job_id: str):
    """Cancel a running init job; the partial scaffold is cleaned up (TASK-362)."""
    from web import init_jobs  # type: ignore

    job = init_jobs.cancel_job(job_id)
    if job is None:
        return _err("not_found", f"no init job {job_id!r}", status=404)
    return {
        "data": {"job_id": job.job_id, "status": job.snapshot()["status"]},
        "meta": {"layer": "hub", "source": "hub.init_job_cancel"},
    }


@router.get("/init-jobs/{job_id}/events")
async def hub_init_job_events(job_id: str):
    """SSE: buffered log replay then live phase/log events until terminal.

    Reconnect-safe — a browser refresh re-attaches with the same job_id and
    replays the buffered log before following (TASK-362)."""
    import asyncio

    from fastapi.responses import StreamingResponse

    from web import init_jobs  # type: ignore

    job = init_jobs.get_job(job_id)
    if job is None:
        return _err("not_found", f"no init job {job_id!r}", status=404)

    def _frame(event: str, payload: dict) -> bytes:
        return f"event: {event}\ndata: {json.dumps(payload)}\n\n".encode("utf-8")

    async def _gen():
        offset = 0
        last_phase = None
        while True:
            snap = job.snapshot(log_tail=0)
            lines, offset = await asyncio.to_thread(job.log_slice, offset)
            for line in lines:
                yield _frame("log", {"line": line})
            if snap["phase"] != last_phase:
                last_phase = snap["phase"]
                yield _frame("phase", {"phase": last_phase, "phases": snap["phases"]})
            if snap["status"] != "running":
                yield _frame(
                    snap["status"],
                    {
                        "status": snap["status"],
                        "error": snap["error"],
                        "result": snap["result"],
                        "cleanup": snap["cleanup"],
                    },
                )
                return
            await asyncio.sleep(0.25)

    return StreamingResponse(
        _gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.patch("/registry/{slug}")
def hub_registry_rename(slug: str, new_slug: str = Body(..., embed=True)):
    """Rename a project's slug (temp-slug → real name; path untouched)."""
    if not _PROJECT_NAME_RE.match((new_slug or "").strip()):
        return _err("validation", "new_slug must match ^[a-z0-9][a-z0-9._-]{0,63}$")
    try:
        from cli.registry import rename_project  # type: ignore

        renamed = rename_project(slug, new_slug.strip())
    except Exception as exc:
        return _err("conflict", str(exc), status=409)
    if renamed is None:
        return _err("not_found", f"no project with slug {slug!r}", status=404)
    return {
        "data": {"slug": renamed.slug, "path": renamed.path},
        "meta": {"layer": "hub", "source": "hub.registry_rename"},
    }


# ---------------------------------------------------------------------------
# DELETE /api/hub/registry/{slug}
# ---------------------------------------------------------------------------


@router.delete("/registry/{slug}")
def hub_registry_remove(slug: str):
    """Unregister a project by slug.  Does NOT touch the project on disk."""
    if not slug or not slug.strip():
        return _err("validation", "slug is required")
    try:
        from cli.registry import remove_project  # type: ignore
    except Exception as exc:
        return _err("unavailable", f"cli.registry unavailable: {exc}", status=503)

    try:
        removed = remove_project(slug.strip())
    except Exception as exc:
        return _err("internal", str(exc), status=500)

    if removed is None:
        return _err("not_found", f"no project with slug {slug!r}", status=404)

    return {
        "data": {"slug": removed.slug, "path": removed.path},
        "meta": {"layer": "hub", "source": "hub.registry_remove"},
    }


# ---------------------------------------------------------------------------
# POST /api/hub/registry/scan
# ---------------------------------------------------------------------------

# Hard caps so a malicious/misconfigured scan can't lock the process.
_SCAN_MAX_DEPTH = 6
_SCAN_MAX_VISITED_DIRS = 5000


@router.post("/registry/scan")
def hub_registry_scan(
    root: str = Body(..., embed=True),
    max_depth: int = Body(_SCAN_MAX_DEPTH, embed=True),
    limit: int = Body(50, embed=True),
):
    """Walk a filesystem root and return every `.coding-os/` project found."""
    if not isinstance(root, str) or not root.strip():
        return _err("validation", "root is required")
    try:
        root_path = Path(root).expanduser().resolve()
    except (OSError, RuntimeError) as exc:
        return _err("validation", f"invalid root: {exc}")
    if not root_path.is_dir():
        return _err("not_found", f"root is not a directory: {root_path}", status=404)

    max_depth = max(1, min(_SCAN_MAX_DEPTH, int(max_depth) if max_depth else _SCAN_MAX_DEPTH))
    limit = max(1, min(500, int(limit) if limit else 50))

    _SKIP_DIR_NAMES = {
        ".git",
        ".hg",
        ".svn",
        "node_modules",
        ".venv",
        "venv",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".tox",
        ".nox",
        ".coding-os",  # never recurse INTO a cos state dir
        "dist",
        "build",
        ".next",
        ".turbo",
        "Library",
        "Trash",
        ".Trash",
    }

    # Snapshot registered paths for the "already_registered" annotation.
    registered_paths: set[str] = set()
    try:
        from cli.registry import load_registry  # type: ignore

        for p in load_registry().projects:
            try:
                registered_paths.add(str(Path(p.path).resolve()))
            except (OSError, RuntimeError):
                continue
    except Exception as exc:
        logger.debug("scan: could not snapshot registry: %s", exc)

    hits: list[dict] = []
    visited = 0
    hit_limit_reached = False
    depth_limit_reached = False

    # BFS so shallow hits surface first (a consumer usually cares about
    # "~/code/my-app" before "~/code/my-app/backend/vendor/old/...").
    from collections import deque

    queue: deque[tuple[Path, int]] = deque([(root_path, 0)])
    while queue:
        if len(hits) >= limit:
            hit_limit_reached = True
            break
        if visited >= _SCAN_MAX_VISITED_DIRS:
            break
        current, depth = queue.popleft()
        visited += 1
        if not current.is_dir():
            continue
        if _looks_like_cos_project(current):
            resolved = str(current.resolve())
            hits.append(
                {
                    "path": resolved,
                    "slug": _resolve_slug_from_registry(current),
                    "already_registered": resolved in registered_paths,
                }
            )
            # Don't recurse into a cos project; nested cos repos are
            # extremely rare and the skip keeps scans snappy.
            continue
        if depth >= max_depth:
            depth_limit_reached = True
            continue
        try:
            children = list(current.iterdir())
        except (OSError, PermissionError):
            continue
        for child in children:
            if not child.is_dir():
                continue
            if child.name in _SKIP_DIR_NAMES:
                continue
            if child.name.startswith("."):
                # Don't descend into dotfiles directories (browser caches,
                # editor state); .coding-os is explicitly skipped above.
                continue
            queue.append((child, depth + 1))

    return {
        "data": {
            "root": str(root_path),
            "hits": hits,
            "count": len(hits),
            "visited_dirs": visited,
            "hit_limit_reached": hit_limit_reached,
            "depth_limit_reached": depth_limit_reached,
        },
        "meta": {
            "layer": "hub",
            "source": "hub.registry_scan",
            "max_depth": max_depth,
            "limit": limit,
        },
    }


# ---------------------------------------------------------------------------
# POST /api/hub/registry/gc
# ---------------------------------------------------------------------------


@router.post("/registry/gc")
def hub_registry_gc(
    dry_run: bool = Body(False, embed=True),
):
    """Remove registry entries whose directory no longer exists."""
    try:
        from cli.registry import Registry, load_registry, save_registry  # type: ignore
    except Exception as exc:
        return _err("unavailable", f"cli.registry unavailable: {exc}", status=503)

    try:
        reg = load_registry()
    except Exception as exc:
        return _err("internal", f"load_registry failed: {exc}", status=500)

    kept: list[dict] = []
    removed: list[dict] = []
    for entry in reg.projects:
        path = Path(entry.path)
        alive = _looks_like_cos_project(path)
        item = {"slug": entry.slug, "path": entry.path, "created_at": entry.created_at}
        (kept if alive else removed).append(item)

    if not dry_run and removed:
        reg.projects = [p for p in reg.projects if _looks_like_cos_project(Path(p.path))]
        try:
            save_registry(reg)
        except Exception as exc:
            return _err("internal", f"save_registry failed: {exc}", status=500)

    return {
        "data": {
            "kept": kept,
            "removed": removed,
            "dry_run": bool(dry_run),
            "kept_count": len(kept),
            "removed_count": len(removed),
        },
        "meta": {"layer": "hub", "source": "hub.registry_gc"},
    }


# ---------------------------------------------------------------------------
# GET /api/hub/suggest-roots — surface likely scan roots for the UI
# ---------------------------------------------------------------------------


@router.get("/suggest-roots")
def hub_suggest_roots(depth: int = Query(0)):
    """Return sensible default scan roots for the UI's import wizard."""
    _ = depth  # reserved — currently unused; keeps the route parameter list stable
    candidates: list[Path] = [
        Path(os.environ.get("COS_PROJECT_ROOT") or os.getcwd()).resolve(),
        Path.home() / "code",
        Path.home() / "Projects",
        Path.home() / "Developer",
        Path.home(),
    ]
    seen: set[str] = set()
    suggestions: list[str] = []
    for c in candidates:
        try:
            resolved = str(c.resolve())
        except (OSError, RuntimeError):
            continue
        if resolved in seen:
            continue
        if not c.is_dir():
            continue
        seen.add(resolved)
        suggestions.append(resolved)
    return {
        "data": {"suggestions": suggestions},
        "meta": {"layer": "hub", "source": "hub.suggest_roots"},
    }
