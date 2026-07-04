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
import re
import shutil
import subprocess
import sys
from pathlib import Path

import yaml
from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse

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


def _project_config_skill_list(key: str) -> list[str]:
    try:
        import yaml

        config_path = _project_root() / ".coding-os.yaml"
        if not config_path.is_file():
            return []
        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        return list(config.get(key) or [])
    except Exception as exc:
        logger.debug("%s read failed: %s", key, exc)
        return []


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

        for s in sorted(load_skill_registry(CORE_SKILLS_DIR).values(), key=lambda s: (s.tier, s.name)):
            skills.append(
                _skill_row(
                    s, provenance="core", extras=extras, disabled=disabled,
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
                    _skill_row(s, provenance=f"stack:{sid}", extras=extras, disabled=disabled, stacks=[sid])
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
    installed_agents = set(_project_config_skill_list("agents"))
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
                    {
                        "id": str(m["id"]),
                        "label": str(m.get("label") or m["id"]),
                        "default": is_default,
                    }
                )
                if is_default and not default_model:
                    default_model = str(m["id"])
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
            adapter_id = str(data.get("id") or manifest.parent.name)
            adapters.append(
                {
                    "id": adapter_id,
                    "label": str(data.get("label") or manifest.parent.name),
                    "runtime": runtime,
                    "available": runtime == "in_process",
                    "installed": adapter_id in installed_agents,
                    "glyph": presence.get("hub_glyph"),
                    "color": presence.get("hub_color"),
                    "efforts": [str(e) for e in (data.get("efforts") or [])],
                    "default_effort": str(data.get("default_effort") or ""),
                    "chat_status": chat_status,
                    "models": models,
                    "mcp_config_paths": mcp_config_paths,
                }
            )
    except Exception as exc:
        logger.debug("load adapters failed: %s", exc)

    # in_process adapters first, then alpha — the runnable one leads the picker.
    adapters.sort(key=lambda a: (a["runtime"] != "in_process", a["id"]))
    return {"adapters": adapters, "default_model": default_model, "count": len(adapters)}


# --------------------------------------------------------------------------
# Mutations — stack install/remove, adapter add/remove, MCP add/remove. All
# refuse to run on the coding-os meta-repo (its .coding-os.yaml is DNA, not a
# consumer install) and append an audit row per mutation. MCP add is limited to
# a first-party allow-list — arbitrary/custom/URL/uploaded MCP is the Extension
# Manager (docs/engineering/extension-manager.md), which the Marketplace fronts.
# --------------------------------------------------------------------------

# Ids reach a subprocess argv or a file path, so restrict them to a slug — a
# leading dash can't then be parsed as a CLI option, nor a slash escape a path.
_SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def _safe_id(value: str) -> bool:
    return bool(_SLUG_RE.match(value or ""))

# Curated first-party stdio MCP servers (no secret / extra config needed). The
# pre-Extension-Manager allow-list; the EM registry supersedes it with the
# trust / SSRF / upload machinery for custom + remote servers.
_MCP_ALLOWLIST: list[dict] = [
    {"id": "fetch", "name": "Fetch", "command": "uvx", "args": ["mcp-server-fetch"],
     "description": "Fetch a URL and return its content as markdown."},
    {"id": "git", "name": "Git", "command": "uvx", "args": ["mcp-server-git"],
     "description": "Read, search, and inspect a local git repository."},
    {"id": "sequential-thinking", "name": "Sequential Thinking", "command": "npx",
     "args": ["-y", "@modelcontextprotocol/server-sequential-thinking"],
     "description": "A structured step-by-step reasoning scratchpad."},
    {"id": "playwright", "name": "Playwright", "command": "npx", "args": ["-y", "@playwright/mcp@latest"],
     "description": "Drive a real browser for end-to-end testing and scraping."},
    {"id": "context7", "name": "Context7", "command": "npx", "args": ["-y", "@upstash/context7-mcp"],
     "description": "Up-to-date, version-specific library docs and code examples."},
]


def _cos_bin() -> list[str]:
    found = shutil.which("cos")
    return [found] if found else [sys.executable, "-m", "cli.main"]


def _cos_root() -> Path | None:
    """coding-os package root — the safe cwd for the `python -m cli.main` fallback,
    so a target project's own top-level cli/ can never shadow the real cos."""
    try:
        from cli.list_stacks import TEMPLATES_DIR

        return TEMPLATES_DIR.parent.parent
    except Exception as exc:
        logger.debug("cos root resolution failed: %s", exc)
        return None


def _parse_cos_json(stdout: str) -> dict:
    """Parse a `cos --format json` payload: whole stdout first (indent=2 is
    multi-line), then the last `{`-prefixed line for single-line emitters."""
    text = stdout.strip()
    if not text:
        return {}
    try:
        whole = json.loads(text)
        if isinstance(whole, dict):
            return whole
    except json.JSONDecodeError:
        pass
    for line in reversed(text.splitlines()):
        cand = line.strip()
        if cand.startswith("{"):
            try:
                parsed = json.loads(cand)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                continue
    return {}


def _run_cos(args: list[str], timeout: int = 300) -> tuple[bool, dict, str]:
    """Run `cos <args>` from the coding-os root; return (ok, json-payload, error).

    The project is addressed via an explicit `-d <path>` arg, not cwd, so the
    subprocess cwd stays on the coding-os tree (see _cos_root)."""
    root = _cos_root()
    try:
        proc = subprocess.run(  # noqa: S603 — fixed argv, never shell=True
            [*_cos_bin(), *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(root) if root else None,
        )
    except subprocess.TimeoutExpired:
        return False, {}, f"'{' '.join(args)}' timed out after {timeout}s"
    except OSError as exc:
        return False, {}, f"could not launch cos: {exc}"
    if proc.returncode != 0:
        return False, {}, (proc.stderr or proc.stdout or "command failed").strip()[-400:]
    return True, _parse_cos_json(proc.stdout or ""), ""


def _is_meta_repo(root: Path) -> bool:
    try:
        from cli._init_helpers import is_coding_os_source_tree

        return is_coding_os_source_tree(root)
    except Exception as exc:
        logger.debug("meta-repo probe failed: %s", exc)
        return False


def _fail(status: int, category: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status, content={"ok": False, "error": {"category": category, "message": message}}
    )


def _ok(data: dict) -> JSONResponse:
    return JSONResponse(content={"ok": True, "data": data})


def _meta_block(kind: str) -> JSONResponse | None:
    """Refuse a mutation on the meta-repo — its config is DNA, not a consumer install."""
    if _is_meta_repo(_project_root()):
        return _fail(
            409,
            "conflict",
            f"cannot {kind} on coding-os itself — the meta-repo ships every stack/adapter as a "
            f"template and installs none in the consumer sense. Manage this on a consumer project.",
        )
    return None


def _audit(root: Path, action: str, unit: str, detail: str = "") -> None:
    """Append a what·which·when row per mutation (extension-manager.md § Hub auth)."""
    try:
        from datetime import datetime, timezone

        log = root / ".coding-os" / "extensions-audit.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        row = {"ts": datetime.now(timezone.utc).isoformat(), "action": action, "unit": unit, "detail": detail}
        with log.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
    except OSError as exc:
        logger.debug("audit append failed: %s", exc)


@router.post("/stacks/{stack_id}")
def config_stack_install(stack_id: str) -> JSONResponse:
    """Install a stack into the project (cos add-stack); refuses on the meta-repo."""
    if not _safe_id(stack_id):
        return _fail(400, "validation", "invalid stack id")
    if (blocked := _meta_block("install a stack")) is not None:
        return blocked
    root = _project_root()
    ok, payload, err = _run_cos(["add-stack", stack_id, "-d", str(root), "--format", "json"])
    if not ok:
        # add_stack's registry-miss carries "not found — available:"; a missing
        # .coding-os.yaml / render failure is internal, not a 404 for the id.
        not_found = "not found — available" in err.lower()
        return _fail(404 if not_found else 400, "not_found" if not_found else "internal", err)
    _audit(root, "stack.install", stack_id, str(payload.get("status", "")))
    return _ok(payload)


@router.delete("/stacks/{stack_id}")
def config_stack_remove(stack_id: str) -> JSONResponse:
    """Remove a stack from the project (cos remove-stack); refuses on the meta-repo."""
    if not _safe_id(stack_id):
        return _fail(400, "validation", "invalid stack id")
    if (blocked := _meta_block("remove a stack")) is not None:
        return blocked
    root = _project_root()
    ok, payload, err = _run_cos(["remove-stack", stack_id, "-d", str(root), "--format", "json"])
    if not ok:
        return _fail(400, "internal", err)
    _audit(root, "stack.remove", stack_id, str(payload.get("status", "")))
    return _ok(payload)


@router.post("/adapters/{agent}")
def config_adapter_add(agent: str) -> JSONResponse:
    """Add an agent adapter to the project (cos add-adapter); refuses on the meta-repo."""
    if not _safe_id(agent):
        return _fail(400, "validation", "invalid adapter id")
    if (blocked := _meta_block("add an adapter")) is not None:
        return blocked
    root = _project_root()
    # Idempotent: don't re-run install or write a spurious audit row for a no-op.
    if agent in set(_project_config_skill_list("agents")):
        return _ok({"agent": agent, "status": "already_installed"})
    ok, _payload, err = _run_cos(["add-adapter", agent, "-d", str(root)])
    if not ok:
        # click.Choice rejects an unknown agent with "is not one of".
        bad = "is not one of" in err.lower()
        return _fail(404 if bad else 400, "not_found" if bad else "internal", err)
    _audit(root, "adapter.add", agent)
    return _ok({"agent": agent, "status": "added"})


@router.delete("/adapters/{agent}")
def config_adapter_remove(agent: str) -> JSONResponse:
    """Remove an agent adapter from the project (never the last one); refuses on the meta-repo."""
    if not _safe_id(agent):
        return _fail(400, "validation", "invalid adapter id")
    if (blocked := _meta_block("remove an adapter")) is not None:
        return blocked
    root = _project_root()
    cfg_path = root / ".coding-os.yaml"
    if not cfg_path.exists():
        return _fail(404, "not_found", ".coding-os.yaml not found")
    try:
        data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        return _fail(400, "internal", f"invalid .coding-os.yaml: {exc}")
    agents = [str(a) for a in (data.get("agents") or [])]
    if agent not in agents:
        return _fail(404, "not_found", f"adapter '{agent}' is not installed")
    if len(agents) <= 1:
        return _fail(
            409, "conflict", f"cannot remove '{agent}' — a project needs at least one adapter."
        )
    data["agents"] = [a for a in agents if a != agent]
    cfg_path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False), encoding="utf-8")
    _audit(root, "adapter.remove", agent)
    return _ok(
        {
            "agent": agent,
            "status": "removed",
            "note": f"dropped from agents; its rendered files remain (re-add with cos add-adapter {agent}).",
        }
    )


@router.get("/mcp/catalog")
def config_mcp_catalog() -> dict:
    """First-party allow-list of MCP servers installable from the Hub (pre-Extension-Manager)."""
    root = _project_root()
    installed: set[str] = set()
    mcp = root / ".mcp.json"
    if mcp.exists():
        try:
            data = json.loads(mcp.read_text(encoding="utf-8")) or {}
            installed = set((data.get("mcpServers") or {}).keys())
        except Exception as exc:
            logger.debug("read .mcp.json failed: %s", exc)
    catalog = [{**s, "installed": s["id"] in installed} for s in _MCP_ALLOWLIST]
    return {"servers": catalog, "count": len(catalog)}


@router.post("/mcp")
def config_mcp_add(body: dict = Body(...)) -> JSONResponse:
    """Add a first-party allow-listed MCP server to the project's .mcp.json."""
    if (blocked := _meta_block("add an MCP server")) is not None:
        return blocked
    server_id = str(body.get("id") or "").strip()
    entry = next((s for s in _MCP_ALLOWLIST if s["id"] == server_id), None)
    if entry is None:
        return _fail(
            400,
            "validation",
            f"'{server_id}' is not on the first-party allow-list — custom / URL / uploaded MCP "
            f"servers are handled by the Extension Manager (coming soon).",
        )
    root = _project_root()
    mcp = root / ".mcp.json"
    try:
        data = json.loads(mcp.read_text(encoding="utf-8")) if mcp.exists() else {}
    except Exception as exc:
        return _fail(400, "internal", f"invalid .mcp.json: {exc}")
    if not isinstance(data, dict):
        return _fail(400, "internal", ".mcp.json is not an object")
    servers = data.setdefault("mcpServers", {})
    if not isinstance(servers, dict):
        return _fail(400, "internal", ".mcp.json mcpServers is not an object")
    if server_id in servers:
        return _fail(409, "conflict", f"MCP server '{server_id}' is already configured")
    servers[server_id] = {"command": entry["command"], "args": list(entry["args"])}
    mcp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    _audit(root, "mcp.add", server_id, entry["command"])
    return _ok({"id": server_id, "status": "added"})


@router.delete("/mcp/{name}")
def config_mcp_remove(name: str) -> JSONResponse:
    """Remove an MCP server from the project's .mcp.json (never the managed coding-os one)."""
    if (blocked := _meta_block("remove an MCP server")) is not None:
        return blocked
    if name == "coding-os":
        return _fail(409, "conflict", "the coding-os MCP server is managed by cos and cannot be removed here.")
    if not _safe_id(name):
        return _fail(400, "validation", "invalid MCP server id")
    root = _project_root()
    mcp = root / ".mcp.json"
    if not mcp.exists():
        return _fail(404, "not_found", "no .mcp.json in this project")
    try:
        data = json.loads(mcp.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        return _fail(400, "internal", f"invalid .mcp.json: {exc}")
    servers = data.get("mcpServers") if isinstance(data, dict) else None
    if not isinstance(servers, dict) or name not in servers:
        return _fail(404, "not_found", f"MCP server '{name}' is not configured")
    del servers[name]
    data["mcpServers"] = servers
    mcp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    _audit(root, "mcp.remove", name)
    return _ok({"id": name, "status": "removed"})
