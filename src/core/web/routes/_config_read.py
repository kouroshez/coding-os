"""Read endpoints: installed stacks, skills, MCP servers and adapters."""

from __future__ import annotations

import logging

import yaml
from fastapi import Body
from fastapi.responses import JSONResponse

from ._config_shared import _audit, _project_config_skill_list, _project_root, router

logger = logging.getLogger(__name__)


@router.get("/stacks")
def config_stacks() -> dict:
    """List installed (.coding-os.yaml) + available (registry) tech stacks."""
    root = _project_root()
    installed: list[str] = []
    cfg = root / ".coding-os.yaml"
    if cfg.exists():
        try:
            data = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
            raw = data.get("templates") or []
            if isinstance(raw, list):
                installed = [str(x) for x in raw]
        except Exception as exc:
            logger.debug("read .coding-os.yaml failed: %s", exc)

    available: list[dict] = []
    try:
        from cli.list_stacks import TEMPLATES_DIR
        from cli.stack_registry import load_stack_registry

        reg = load_stack_registry(TEMPLATES_DIR)
        installed_set = set(installed)
        for s in sorted(reg.values(), key=lambda s: s.id):
            available.append(
                {
                    "id": s.id,
                    "label": s.label,
                    "category": s.category,
                    "primary_skill": s.primary_skill,
                    "installed": s.id in installed_set,
                }
            )
    except Exception as exc:
        logger.debug("load_stack_registry failed: %s", exc)

    return {"installed": installed, "available": available, "count": len(available)}


def _project_extra_skills() -> list[str]:
    return _project_config_skill_list("extra_skills")


def _installed_stacks() -> list[dict]:
    """Installed stack ids (.coding-os.yaml::templates) resolved to registry labels."""
    installed = _project_config_skill_list("templates")
    labels: dict[str, str] = {}
    try:
        from cli.list_stacks import TEMPLATES_DIR
        from cli.stack_registry import load_stack_registry

        labels = {s.id: s.label for s in load_stack_registry(TEMPLATES_DIR).values()}
    except Exception as exc:
        logger.debug("stack labels unavailable: %s", exc)
    return [{"id": sid, "label": labels.get(sid, sid)} for sid in installed]


def _skill_stack_membership(installed_ids: list[str]) -> dict[str, set[str]]:
    """skill_name -> installed stacks that require/recommend it (the grouped view)."""
    membership: dict[str, set[str]] = {}
    try:
        from cli.skills_list import collect_stack_skill_groups
    except Exception:
        return membership
    for sid in installed_ids:
        try:
            groups = collect_stack_skill_groups(sid)["groups"]
        except Exception as exc:
            logger.debug("stack skill groups for %s unavailable: %s", sid, exc)
            continue
        names = {e["name"] for e in groups["required"]} | {e["name"] for e in groups["recommended"]}
        for name in names:
            membership.setdefault(name, set()).add(sid)
    return membership


def _skill_row(profile, *, provenance: str, extras: set, disabled: set, stacks: list[str]) -> dict:
    return {
        "name": profile.name,
        "description": profile.description,
        "tier": profile.tier,
        "domain": list(profile.domain),
        "globs": profile.globs,
        "phase": profile.phase,
        "extra": profile.name in extras,
        # provenance + disabled let the Hub render Enable/Disable for core/stack
        # skills (opt-out via disabled_skills), not just the community add/remove
        # path; `stacks` powers the grouped-by-stack view.
        "provenance": provenance,
        "disabled": profile.name in disabled,
        "stacks": stacks,
    }


@router.get("/skills")
def config_skills() -> dict:
    """List active skills (core + installed-stack) with their stack membership + project extras."""
    extras = set(_project_extra_skills())
    disabled = set(_project_config_skill_list("disabled_skills"))
    installed = _installed_stacks()
    installed_ids = [s["id"] for s in installed]
    membership = _skill_stack_membership(installed_ids)

    skills: list[dict] = []
    seen: set[str] = set()
    try:
        from cli.skill_registry import load_skill_registry
        from cli.skills_list import CORE_SKILLS_DIR, TEMPLATES_DIR

        for s in sorted(
            load_skill_registry(CORE_SKILLS_DIR).values(), key=lambda s: (s.tier, s.name)
        ):
            skills.append(
                _skill_row(
                    s,
                    provenance="core",
                    extras=extras,
                    disabled=disabled,
                    stacks=sorted(membership.get(s.name, set())),
                )
            )
            seen.add(s.name)
        # Skills shipped by an installed stack's own templates dir (e.g. meta →
        # python-meta-server) that the core registry does not carry.
        for sid in installed_ids:
            stack_dir = TEMPLATES_DIR / sid / "skills"
            if not stack_dir.is_dir():
                continue
            for s in sorted(load_skill_registry(stack_dir).values(), key=lambda s: s.name):
                if s.name in seen:
                    continue
                skills.append(
                    _skill_row(
                        s, provenance=f"stack:{sid}", extras=extras, disabled=disabled, stacks=[sid]
                    )
                )
                seen.add(s.name)
    except Exception as exc:
        logger.debug("load skills failed: %s", exc)

    return {
        "skills": skills,
        "count": len(skills),
        "extra_skills": sorted(extras),
        "disabled_skills": sorted(disabled),
        "installed_stacks": installed,
    }


@router.patch("/skills/{skill_name}")
def config_skill_toggle(skill_name: str, body: dict = Body(...)) -> JSONResponse:
    """Enable/disable a project extra skill — round-trips to .coding-os.yaml."""
    enabled = body.get("enabled")
    if not isinstance(enabled, bool):
        return JSONResponse(
            status_code=400,
            content={
                "ok": False,
                "error": {"category": "validation", "message": "body must be {'enabled': bool}"},
            },
        )
    try:
        import click as _click

        from cli.skill_commands import set_project_skill

        outcome = set_project_skill(_project_root(), skill_name, enabled=enabled)
    except _click.ClickException as exc:
        return JSONResponse(
            status_code=404 if "unknown skill" in exc.message else 400,
            content={"ok": False, "error": {"category": "validation", "message": exc.message}},
        )
    return JSONResponse(content={"ok": True, "data": outcome})


@router.get("/mcp")
def config_mcp() -> dict:
    """List every MCP server this machine declares, project and global, by scope."""
    from core.web.routes._config_mcp import (
        GLOBAL_SCOPE,
        MANAGED_ADAPTERS,
        PROJECT_SCOPE,
        inventory,
    )

    servers = inventory(_project_root())
    return {
        "servers": servers,
        "count": len(servers),
        "scopes": {
            PROJECT_SCOPE: sum(1 for s in servers if s["scope"] == PROJECT_SCOPE),
            GLOBAL_SCOPE: sum(1 for s in servers if s["scope"] == GLOBAL_SCOPE),
        },
        "adapters": {
            adapter: sum(1 for s in servers if s["adapter"] == adapter)
            for adapter in MANAGED_ADAPTERS
        },
    }


@router.get("/adapters")
def config_adapters() -> dict:
    """List agent adapters and the chat models each declares (adapter→models SSOT)."""
    from thinking_os import supervision
    from thinking_os.adapter_registry import load_adapter_records
    from web._project_context import current_db_path
    from web.routes._config_adapters import (
        probe_chat,
        probe_dispatch,
        probe_transcript,
        resolve_models,
    )

    adapters: list[dict] = []
    default_model = ""
    installed_agents = set(_project_config_skill_list("agents"))
    routing_enabled = supervision.enabled(_project_root())
    health = supervision.health_snapshot(current_db_path()) if routing_enabled else {}
    try:
        for record in load_adapter_records().values():
            data = record.manifest
            runtime = str(data.get("runtime") or "roadmap")
            models = resolve_models(record)
            for model in models:
                if model["default"] and not default_model:
                    default_model = model["id"]
            presence = data.get("presence") if isinstance(data.get("presence"), dict) else {}
            cs = data.get("chat_status") if isinstance(data.get("chat_status"), dict) else {}
            tool_labels = cs.get("tool_labels") if isinstance(cs.get("tool_labels"), dict) else {}
            chat_status = {
                "tool_labels": {str(k): str(v) for k, v in tool_labels.items()},
                "idle_phrases": [str(x) for x in (cs.get("idle_phrases") or [])],
            }
            ml = data.get("mcp_launch") if isinstance(data.get("mcp_launch"), dict) else {}
            seen_paths: set[str] = set()
            mcp_config_paths: list[str] = []
            for cp in ml.get("config_paths") or []:
                if isinstance(cp, dict) and cp.get("path"):
                    path = str(cp["path"])
                    if path not in seen_paths:
                        seen_paths.add(path)
                        mcp_config_paths.append(path)
            adapter_id = record.id
            chat = probe_chat(record)
            dispatch = probe_dispatch(record)
            transcript = probe_transcript(record)
            adapter_health = supervision.adapter_health(health, adapter_id) or {
                "state": "healthy" if routing_enabled else "disabled",
                "failure_count": 0,
                "retry_after_s": 0,
                "probe_active": False,
                "reason": "",
            }
            adapters.append(
                {
                    "id": adapter_id,
                    "label": str(data.get("label") or adapter_id),
                    "runtime": runtime,
                    # `available` is the chat verdict the pickers already read;
                    # it now comes from probing the provider, not from `runtime`.
                    "available": chat["available"],
                    "chat_available": chat["available"],
                    "chat_declared": chat["declared"],
                    "chat_missing": chat["missing"],
                    "chat_remedy": chat["remedy"],
                    "installed": adapter_id in installed_agents,
                    "dispatch_declared": dispatch["declared"],
                    "dispatch_available": dispatch["available"],
                    "dispatch_missing": dispatch["missing"],
                    "dispatch_remedy": dispatch["remedy"],
                    "transcript_available": transcript["available"],
                    "transcript_declared": transcript["declared"],
                    "transcript_missing": transcript["missing"],
                    "transcript_remedy": transcript["remedy"],
                    "capabilities": sorted(record.capabilities),
                    "health": adapter_health,
                    "glyph": presence.get("hub_glyph"),
                    "color": presence.get("hub_color"),
                    "efforts": list(record.efforts),
                    "default_effort": str(data.get("default_effort") or ""),
                    "chat_status": chat_status,
                    "models": models,
                    "mcp_config_paths": mcp_config_paths,
                }
            )
    except Exception as exc:
        logger.debug("load adapters failed: %s", exc)

    # in_process adapters first, then alpha — the runnable one leads the picker.
    # Runnable adapters lead the picker; among equals, alphabetical.
    adapters.sort(key=lambda a: (not (a["chat_available"] or a["dispatch_available"]), a["id"]))
    return {"adapters": adapters, "default_model": default_model, "count": len(adapters)}


@router.delete("/adapters/{adapter_id}/health")
def config_adapter_health_clear(adapter_id: str):
    from thinking_os import supervision
    from thinking_os.adapter_registry import load_adapter_records
    from web._project_context import current_db_path

    if adapter_id not in load_adapter_records():
        return JSONResponse(
            status_code=404,
            content={"ok": False, "error": {"category": "not_found", "message": "unknown adapter"}},
        )
    cleared = supervision.clear_health(current_db_path(), adapter_id)
    _audit(_project_root(), "adapter.health.clear", adapter_id, str(cleared))
    return {"ok": True, "data": {"adapter": adapter_id, "cleared": cleared}}


# --------------------------------------------------------------------------
# Mutations — stack install/remove, adapter add/remove, MCP add/remove. Each
# edits the ACTIVE project (current_project_root) and appends an audit row. They
# run on coding-os too — the CLI already protects the hand-written AGENTS.md
# there. MCP add is limited to a first-party allow-list; arbitrary/custom/URL/
# uploaded MCP is the Extension Manager (docs/engineering/extension-manager.md),
# which the Marketplace fronts.
# --------------------------------------------------------------------------

# Ids reach a subprocess argv or a file path, so restrict them to a slug — a
