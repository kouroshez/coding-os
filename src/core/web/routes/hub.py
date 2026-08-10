"""core.web.routes.hub — global Hub registry endpoints.

Facade: the read-only catalog + registry-mutation endpoints live here, and the
create flow and the import/scan flow decorate the same router from the sibling
modules imported at the foot of this file, so `from ...hub import router` still
yields a router carrying every /api/hub route.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import Body

from ._hub_shared import (
    _PROJECT_NAME_RE as _PROJECT_NAME_RE,
    _ancestor_with_coding_os as _ancestor_with_coding_os,
    _derive_runtime_entry as _derive_runtime_entry,
    _err as _err,
    _is_hub_state_dir as _is_hub_state_dir,
    _is_meta_repo as _is_meta_repo,
    _is_registered_project as _is_registered_project,
    _looks_like_cos_project as _looks_like_cos_project,
    _resolve_slug_from_registry as _resolve_slug_from_registry,
    _validate_project_path as _validate_project_path,
    router as router,
)

logger = logging.getLogger("coding_os.web.hub")


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


@router.get("/agents")
def hub_agents() -> dict:
    """Cross-project live-agent roster — one group per registered project (TASK-437)."""
    from web.routes.presence import cross_project_agents  # type: ignore

    groups = cross_project_agents()
    return {"projects": groups, "count": sum(len(g["agents"]) for g in groups)}


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
    adapters = [{"id": a.id, "label": a.label} for a in sorted(reg.values(), key=lambda a: a.id)]
    return {
        "data": {"adapters": adapters, "count": len(adapters)},
        "meta": {"layer": "hub", "source": "hub.adapters"},
    }


@router.get("/modules")
def hub_modules() -> dict:
    """List subsystem modules (data-driven from src/core/subsystems.yaml) for the Composer."""
    try:
        from cli.subsystems import (  # type: ignore
            load_profiles,
            load_subsystems,
            resolve_profile,
        )

        registry = load_subsystems()
        _, default_profile = load_profiles()
        default_disabled = resolve_profile(default_profile)
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
        if not m.hidden
    ]
    visible = {m["id"] for m in modules}
    return {
        "data": {
            "modules": modules,
            "count": len(modules),
            "default_profile": default_profile,
            "default_disabled": [m for m in default_disabled if m in visible],
        },
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
    templates_root = TEMPLATES_DIR.resolve()
    presets = [
        {
            "id": p.id,
            "label": p.label,
            "description": p.description,
            "stacks": list(p.stacks),
            "provenance": (
                "core" if p.source_path.resolve().is_relative_to(templates_root) else "user"
            ),
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


# The part modules decorate `router` above; importing them here is what
# registers /api/hub/registry/init, /init-jobs/*, /registry/scan, /registry/gc
# and /suggest-roots. Re-exported names keep `from ...hub import X` resolving.
from ._hub_init import (  # noqa: E402
    _build_cos_init_cmd as _build_cos_init_cmd,
    _cos_init_command as _cos_init_command,
    _default_profile_reenables as _default_profile_reenables,
    _parse_init_payload as _parse_init_payload,
    _resolve_agents as _resolve_agents,
    _validate_init_inputs as _validate_init_inputs,
)
from ._hub_init_routes import (  # noqa: E402
    _run_cos_init as _run_cos_init,
    hub_init_job_cancel as hub_init_job_cancel,
    hub_init_job_events as hub_init_job_events,
    hub_init_job_snapshot as hub_init_job_snapshot,
    hub_registry_init as hub_registry_init,
    hub_registry_validate_init as hub_registry_validate_init,
)
from ._hub_scan import (  # noqa: E402
    hub_registry_gc as hub_registry_gc,
    hub_registry_scan as hub_registry_scan,
    hub_suggest_roots as hub_suggest_roots,
)
