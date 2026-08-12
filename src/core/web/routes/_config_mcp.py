"""MCP server inventory and mutation for the Hub Config tab.

One reason to change: how MCP servers are discovered, described, and written.

Two facts drove the shape. A survey of this machine's real configs found 3
servers declared globally and invisible to a project-scoped reader, and 6 of 14
project servers using an HTTP/SSE transport that a `command`+`args`-only reader
renders as a blank row and a writer cannot express at all.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

PROJECT_SCOPE = "project"
GLOBAL_SCOPE = "global"
# Claude's user-level config. Codex keeps its own servers in ~/.codex/config.toml
# (TOML, different key shape); it is listed as a known gap rather than guessed at,
# because writing a format we have not modelled is how a config gets corrupted.
GLOBAL_CONFIG_PATH = Path.home() / ".claude.json"
PROJECT_CONFIG_NAME = ".mcp.json"

STDIO_TRANSPORT = "stdio"
REMOTE_TRANSPORTS = ("http", "sse")


def describe_transport(spec: dict) -> str:
    """Classify a server entry as stdio or its declared remote transport."""
    declared = str(spec.get("type") or "").strip().lower()
    if declared in REMOTE_TRANSPORTS:
        return declared
    if spec.get("url"):
        return "http"
    return STDIO_TRANSPORT


def _read_servers(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8")) or {}
    except (OSError, ValueError) as exc:
        logger.debug("read %s failed: %s", path, exc)
        return {}
    servers = data.get("mcpServers")
    return servers if isinstance(servers, dict) else {}


def _as_row(name: str, spec: dict, scope: str) -> dict:
    spec = spec if isinstance(spec, dict) else {}
    transport = describe_transport(spec)
    return {
        "name": name,
        "scope": scope,
        "transport": transport,
        # Remote servers have no command; a UI that only reads command/args
        # rendered them as blank rows, which is how 6 of 14 went unnoticed.
        "command": spec.get("command"),
        "args": list(spec.get("args") or []),
        "url": spec.get("url"),
        "managed": name == "coding-os",
    }


def inventory(project_root: Path, *, global_path: Path | None = None) -> list[dict]:
    """Every MCP server this machine declares, project first, each labelled by scope."""
    rows = [
        _as_row(name, spec, PROJECT_SCOPE)
        for name, spec in _read_servers(project_root / PROJECT_CONFIG_NAME).items()
    ]
    project_names = {row["name"] for row in rows}
    for name, spec in _read_servers(global_path or GLOBAL_CONFIG_PATH).items():
        row = _as_row(name, spec, GLOBAL_SCOPE)
        # A project entry of the same name wins at runtime; saying so beats
        # showing the same server twice with no hint which one is live.
        row["shadowed_by_project"] = name in project_names
        rows.append(row)
    return rows


def validate_server_spec(name: str, spec: dict) -> str | None:
    """Return a human reason the spec is unusable, or None when it is well-formed."""
    if not name:
        return "server name is required"
    transport = describe_transport(spec)
    if transport == STDIO_TRANSPORT:
        if not str(spec.get("command") or "").strip():
            return "a stdio server needs a command"
        if not isinstance(spec.get("args") or [], list):
            return "args must be a list"
        return None
    url = str(spec.get("url") or "").strip()
    if not url:
        return f"a {transport} server needs a url"
    if not url.startswith(("http://", "https://")):
        return "url must be http:// or https://"
    return None


def normalize_server_spec(spec: dict) -> dict:
    """Reduce a submitted spec to the keys the transport actually uses."""
    transport = describe_transport(spec)
    if transport == STDIO_TRANSPORT:
        entry = {"command": str(spec["command"]).strip(), "args": list(spec.get("args") or [])}
        env = spec.get("env")
        if isinstance(env, dict) and env:
            entry["env"] = {str(k): str(v) for k, v in env.items()}
        return entry
    entry = {"type": transport, "url": str(spec["url"]).strip()}
    headers = spec.get("headers")
    if isinstance(headers, dict) and headers:
        entry["headers"] = {str(k): str(v) for k, v in headers.items()}
    return entry


def config_path_for_scope(
    project_root: Path, scope: str, *, global_path: Path | None = None
) -> Path:
    return (
        (global_path or GLOBAL_CONFIG_PATH)
        if scope == GLOBAL_SCOPE
        else project_root / PROJECT_CONFIG_NAME
    )


def write_server(path: Path, name: str, entry: dict) -> None:
    """Add or replace one server, preserving every other key in the file."""
    # Read-modify-write on the whole document: the global config holds unrelated
    # user state, and rewriting only `mcpServers` would discard it.
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, ValueError) as exc:
        raise ValueError(f"{path.name} is not readable JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{path.name} is not an object")
    servers = data.setdefault("mcpServers", {})
    if not isinstance(servers, dict):
        raise ValueError(f"{path.name} mcpServers is not an object")
    servers[name] = entry
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def remove_server(path: Path, name: str) -> bool:
    """Drop one server. Returns False when it was not there to begin with."""
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, ValueError) as exc:
        raise ValueError(f"{path.name} is not readable JSON: {exc}") from exc
    servers = data.get("mcpServers") if isinstance(data, dict) else None
    if not isinstance(servers, dict) or name not in servers:
        return False
    del servers[name]
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return True
