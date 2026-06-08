"""core.web.routes.config — read-only per-project Configuration surface.

Surfaces what is configured for the active project so a human can SEE it
without reading YAML/JSON: tech stacks (.coding-os.yaml::templates + the stack
registry), skills (the core skill registry), and MCP servers (.mcp.json).

Read-only this phase. Per-project enable/disable for skills/MCP/hooks is a
separate kernel-override epic (a Hub toggle must never edit the global
registry). Hooks already have /api/hooks/list, so they are not duplicated here.

Available stacks/skills are read from the installed package (CODING_OS_ROOT),
not the project tree, so the surface works identically in the meta-repo and in
a scaffolded consumer that has no src/templates of its own.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import yaml
from fastapi import APIRouter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/config", tags=["config"])


def _project_root() -> Path:
    from web._project_context import current_project_root

    return current_project_root()


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


@router.get("/skills")
def config_skills() -> dict:
    """List the core skill registry (name, tier, domain, globs, phase)."""
    skills: list[dict] = []
    try:
        from cli.skill_registry import load_skill_registry
        from cli.skills_list import CORE_SKILLS_DIR

        reg = load_skill_registry(CORE_SKILLS_DIR)
        for s in sorted(reg.values(), key=lambda s: (s.tier, s.name)):
            skills.append(
                {
                    "name": s.name,
                    "description": s.description,
                    "tier": s.tier,
                    "domain": list(s.domain),
                    "globs": s.globs,
                    "phase": s.phase,
                }
            )
    except Exception as exc:
        logger.debug("load_skill_registry failed: %s", exc)

    return {"skills": skills, "count": len(skills)}


@router.get("/mcp")
def config_mcp() -> dict:
    """List MCP servers configured in the project's .mcp.json."""
    root = _project_root()
    servers: list[dict] = []
    mcp = root / ".mcp.json"
    if mcp.exists():
        try:
            data = json.loads(mcp.read_text(encoding="utf-8")) or {}
            raw = data.get("mcpServers") or {}
            if isinstance(raw, dict):
                for name, spec in raw.items():
                    spec = spec if isinstance(spec, dict) else {}
                    servers.append(
                        {
                            "name": name,
                            "command": spec.get("command"),
                            "args": spec.get("args") or [],
                            "managed": name == "coding-os",
                        }
                    )
        except Exception as exc:
            logger.debug("read .mcp.json failed: %s", exc)

    return {"servers": servers, "count": len(servers)}


@router.get("/adapters")
def config_adapters() -> dict:
    """List agent adapters and the chat models each declares (adapter→models SSOT)."""
    adapters: list[dict] = []
    default_model = ""
    try:
        from cli.list_stacks import TEMPLATES_DIR

        adapters_dir = TEMPLATES_DIR.parent / "adapters"
        for manifest in sorted(adapters_dir.glob("*/adapter.yaml")):
            try:
                data = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
            except Exception as exc:
                logger.debug("read %s failed: %s", manifest, exc)
                continue
            runtime = str(data.get("runtime") or "roadmap")
            models: list[dict] = []
            for m in data.get("models") or []:
                if not isinstance(m, dict) or not m.get("id"):
                    continue
                is_default = bool(m.get("default"))
                models.append(
                    {"id": str(m["id"]), "label": str(m.get("label") or m["id"]), "default": is_default}
                )
                if is_default and not default_model:
                    default_model = str(m["id"])
            presence = data.get("presence") if isinstance(data.get("presence"), dict) else {}
            adapters.append(
                {
                    "id": str(data.get("id") or manifest.parent.name),
                    "label": str(data.get("label") or manifest.parent.name),
                    "runtime": runtime,
                    "available": runtime == "in_process",
                    "glyph": presence.get("hub_glyph"),
                    "color": presence.get("hub_color"),
                    "efforts": [str(e) for e in (data.get("efforts") or [])],
                    "default_effort": str(data.get("default_effort") or ""),
                    "models": models,
                }
            )
    except Exception as exc:
        logger.debug("load adapters failed: %s", exc)

    # in_process adapters first, then alpha — the runnable one leads the picker.
    adapters.sort(key=lambda a: (a["runtime"] != "in_process", a["id"]))
    return {"adapters": adapters, "default_model": default_model, "count": len(adapters)}
