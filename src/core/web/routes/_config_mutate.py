"""Mutation endpoints: stack install/remove, adapter add/remove, MCP add/remove."""

from __future__ import annotations

import json
import logging

import yaml
from fastapi import Body
from fastapi.responses import JSONResponse

from ._config_shared import (
    _MCP_ALLOWLIST,
    _audit,
    _fail,
    _ok,
    _project_config_skill_list,
    _project_root,
    _run_cos,
    _safe_id,
    router,
)

logger = logging.getLogger(__name__)


@router.post("/stacks/{stack_id}")
def config_stack_install(stack_id: str) -> JSONResponse:
    """Install a stack into the active project (cos add-stack)."""
    if not _safe_id(stack_id):
        return _fail(400, "validation", "invalid stack id")
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
    """Remove a stack from the active project (cos remove-stack)."""
    if not _safe_id(stack_id):
        return _fail(400, "validation", "invalid stack id")
    root = _project_root()
    ok, payload, err = _run_cos(["remove-stack", stack_id, "-d", str(root), "--format", "json"])
    if not ok:
        return _fail(400, "internal", err)
    _audit(root, "stack.remove", stack_id, str(payload.get("status", "")))
    return _ok(payload)


@router.post("/adapters/{agent}")
def config_adapter_add(agent: str) -> JSONResponse:
    """Add an agent adapter to the active project (cos add-adapter)."""
    if not _safe_id(agent):
        return _fail(400, "validation", "invalid adapter id")
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
    """Remove an agent adapter from the active project (never the last one)."""
    if not _safe_id(agent):
        return _fail(400, "validation", "invalid adapter id")
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
    cfg_path.write_text(
        yaml.dump(data, default_flow_style=False, sort_keys=False), encoding="utf-8"
    )
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
    """Add a first-party allow-listed MCP server to the active project's .mcp.json."""
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
    """Remove an MCP server from the active project's .mcp.json (never the managed coding-os one)."""
    if name == "coding-os":
        return _fail(
            409,
            "conflict",
            "the coding-os MCP server is managed by cos and cannot be removed here.",
        )
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
