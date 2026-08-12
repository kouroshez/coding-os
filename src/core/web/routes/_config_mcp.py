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
# Claude's user-level config. Codex keeps its own servers as TOML tables in
# ~/.codex/config.toml and is edited through _config_codex_toml, which appends and
# span-deletes rather than round-tripping, so hand-written comments survive.
GLOBAL_CONFIG_PATH = Path.home() / ".claude.json"
PROJECT_CONFIG_NAME = ".mcp.json"

STDIO_TRANSPORT = "stdio"
REMOTE_TRANSPORTS = ("http", "sse")

CLAUDE_ADAPTER = "claude"
CODEX_ADAPTER = "codex"
MANAGED_ADAPTERS = (CLAUDE_ADAPTER, CODEX_ADAPTER)


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


def codex_config_path() -> Path:
    return Path.home() / ".codex" / "config.toml"


def _codex_rows() -> list[dict]:
    from core.web.routes import _config_codex_toml as codex

    rows = []
    for name, spec in codex.read_servers(codex_config_path()).items():
        row = _as_row(name, spec, GLOBAL_SCOPE)
        row["adapter"] = CODEX_ADAPTER
        rows.append(row)
    return rows


def inventory(project_root: Path, *, global_path: Path | None = None) -> list[dict]:
    """Every MCP server this machine declares, labelled by adapter and scope."""
    rows = [
        {**_as_row(name, spec, PROJECT_SCOPE), "adapter": CLAUDE_ADAPTER}
        for name, spec in _read_servers(project_root / PROJECT_CONFIG_NAME).items()
    ]
    project_names = {row["name"] for row in rows}
    for name, spec in _read_servers(global_path or GLOBAL_CONFIG_PATH).items():
        row = {**_as_row(name, spec, GLOBAL_SCOPE), "adapter": CLAUDE_ADAPTER}
        # A project entry of the same name wins at runtime; saying so beats
        # showing the same server twice with no hint which one is live.
        row["shadowed_by_project"] = name in project_names
        rows.append(row)
    rows.extend(_codex_rows())
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


def effective_scope(adapter: str, scope: str) -> str:
    """The scope a write will actually land in — Codex has no project-level config."""
    return GLOBAL_SCOPE if adapter == CODEX_ADAPTER else scope


def write_for_adapter(project_root: Path, adapter: str, scope: str, name: str, entry: dict) -> None:
    """Add one server in the format the chosen adapter actually reads."""
    if adapter == CODEX_ADAPTER:
        from core.web.routes import _config_codex_toml as codex

        codex.write_server(codex_config_path(), name, entry)
        return
    write_server(config_path_for_scope(project_root, scope), name, entry)


def remove_for_adapter(project_root: Path, adapter: str, scope: str, name: str) -> bool:
    if adapter == CODEX_ADAPTER:
        from core.web.routes import _config_codex_toml as codex

        return codex.remove_server(codex_config_path(), name)
    return remove_server(config_path_for_scope(project_root, scope), name)


def existing_names(project_root: Path, adapter: str, scope: str) -> set[str]:
    if adapter == CODEX_ADAPTER:
        from core.web.routes import _config_codex_toml as codex

        return set(codex.read_servers(codex_config_path()))
    return set(_read_servers(config_path_for_scope(project_root, scope)))


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
