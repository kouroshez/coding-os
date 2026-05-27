"""graph_os — JSON extractor.

Targets: package.json, tsconfig.json, mcp.json, settings.json, eslintrc.json,
plus generic .json configs. Path-aware: emits richer edges for well-known file
names (npm deps, tsconfig path aliases, MCP server registrations).

Tolerant: malformed JSON degrades to a single file node with a parse_error.
Stdlib parser only — no third-party deps.

Spec: docs/playbooks/polyglot-extractor-roadmap.md §4.6 (Epic B1).
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import PurePosixPath
from typing import Any

from ..types import EvidenceSignal, GraphEdge, GraphNode
from .md_links import (
    ExtractionResult,
    ParseError,
    _normalize_path,
    _promote_stubs,
    emit_contains_spine,
)

logger = logging.getLogger("graph_os.extractors.code_json")
EXTRACTOR_ID = "code_json@v1"

# Strip // and /* */ comments so tsconfig.json (de-facto JSON5) parses cleanly.
_LINE_COMMENT_RE = re.compile(r"//[^\n]*")
_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
_TRAILING_COMMA_RE = re.compile(r",(\s*[\]\}])")


def file_uid(path: str) -> str:
    return f"code:file:{_normalize_path(path)}"


def _config_uid(path: str, pointer: str) -> str:
    return f"config:json:{_normalize_path(path)}#{pointer}"


def _strip_jsonc(content: str) -> str:
    """Strip // line comments + /* */ block comments + trailing commas."""
    out = _BLOCK_COMMENT_RE.sub("", content)
    out = _LINE_COMMENT_RE.sub("", out)
    out = _TRAILING_COMMA_RE.sub(r"\1", out)
    return out


def _parse_lenient(content: str) -> tuple[Any | None, str | None]:
    """Parse JSON, falling back to JSON5-like stripping on failure."""
    try:
        return json.loads(content), None
    except json.JSONDecodeError as exc:
        try:
            return json.loads(_strip_jsonc(content)), None
        except json.JSONDecodeError as exc2:
            return None, f"{exc2.msg} at line {exc2.lineno}, col {exc2.colno}"


# ---------------------------------------------------------------------------
# Per-file-kind emitters
# ---------------------------------------------------------------------------


def _emit_package_json(
    data: dict[str, Any],
    path: str,
    normalised: str,
    file_uid_: str,
    result: ExtractionResult,
) -> None:
    name = str(data.get("name", "")).strip()
    if name:
        pkg_uid = f"npm:package:{name}"
        result.nodes.append(
            GraphNode(
                uid=pkg_uid,
                # W7.7 / R4-N6: dep nodes use `dependency` kind so they
                # are queryable separately from HTTP/MCP contracts.
                kind="dependency",
                label=name,
                file_path=normalised,
                lang="json",
                metadata={"extractor": EXTRACTOR_ID, "subkind": "npm_package"},
            )
        )
        result.edges.append(
            GraphEdge(
                source_uid=file_uid_,
                target_uid=pkg_uid,
                edge_type="declares",
                extractor=EXTRACTOR_ID,
                confidence=1.0,
            )
        )
    for dep_key in ("dependencies", "devDependencies", "peerDependencies"):
        deps = data.get(dep_key)
        if not isinstance(deps, dict):
            continue
        for dep_name in deps.keys():
            if not isinstance(dep_name, str) or not dep_name:
                continue
            target = f"npm:package:{dep_name}"
            result.edges.append(
                GraphEdge(
                    source_uid=file_uid_,
                    target_uid=target,
                    edge_type="imports",
                    extractor=EXTRACTOR_ID,
                    confidence=0.95,
                    evidence=(EvidenceSignal(dep_key, 0.95),),
                )
            )
    scripts = data.get("scripts")
    if isinstance(scripts, dict):
        for script_name in scripts.keys():
            if not isinstance(script_name, str) or not script_name:
                continue
            uid = _config_uid(path, f"/scripts/{script_name}")
            result.nodes.append(
                GraphNode(
                    uid=uid,
                    kind="tool",
                    label=f"npm:{script_name}",
                    file_path=normalised,
                    lang="json",
                    metadata={"extractor": EXTRACTOR_ID, "subkind": "npm_script"},
                )
            )
            result.edges.append(
                GraphEdge(
                    source_uid=file_uid_,
                    target_uid=uid,
                    edge_type="contains",
                    extractor=EXTRACTOR_ID,
                    confidence=1.0,
                )
            )


def _emit_tsconfig_json(
    data: dict[str, Any],
    path: str,
    normalised: str,
    file_uid_: str,
    result: ExtractionResult,
) -> None:
    extends = data.get("extends")
    if isinstance(extends, str) and extends:
        origin_dir = PurePosixPath(normalised).parent
        rel = extends if extends.endswith(".json") else f"{extends}.json"
        resolved = (origin_dir / rel).as_posix()
        result.edges.append(
            GraphEdge(
                source_uid=file_uid_,
                target_uid=f"code:file:{resolved}",
                edge_type="imports",
                extractor=EXTRACTOR_ID,
                confidence=0.85,
                evidence=(EvidenceSignal("tsconfig_extends", 0.85),),
            )
        )
    compiler = data.get("compilerOptions") or {}
    paths = compiler.get("paths") if isinstance(compiler, dict) else None
    if isinstance(paths, dict):
        for alias in paths.keys():
            if not isinstance(alias, str):
                continue
            uid = _config_uid(path, f"/compilerOptions/paths/{alias}")
            result.nodes.append(
                GraphNode(
                    uid=uid,
                    kind="contract",
                    label=alias,
                    file_path=normalised,
                    lang="json",
                    metadata={"extractor": EXTRACTOR_ID, "subkind": "ts_path_alias"},
                )
            )
            result.edges.append(
                GraphEdge(
                    source_uid=file_uid_,
                    target_uid=uid,
                    edge_type="declares",
                    extractor=EXTRACTOR_ID,
                    confidence=1.0,
                )
            )


def _emit_mcp_json(
    data: dict[str, Any],
    path: str,
    normalised: str,
    file_uid_: str,
    result: ExtractionResult,
) -> None:
    servers = data.get("mcpServers")
    if not isinstance(servers, dict):
        return
    for srv_name in servers.keys():
        if not isinstance(srv_name, str):
            continue
        uid = f"mcp:server:{srv_name}"
        result.nodes.append(
            GraphNode(
                uid=uid,
                kind="contract",
                label=srv_name,
                file_path=normalised,
                lang="json",
                metadata={"extractor": EXTRACTOR_ID, "subkind": "mcp_server"},
            )
        )
        result.edges.append(
            GraphEdge(
                source_uid=file_uid_,
                target_uid=uid,
                edge_type="declares",
                extractor=EXTRACTOR_ID,
                confidence=1.0,
            )
        )


def _emit_settings_json(
    data: dict[str, Any],
    path: str,
    normalised: str,
    file_uid_: str,
    result: ExtractionResult,
) -> None:
    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        return
    for event_name in hooks.keys():
        if not isinstance(event_name, str):
            continue
        uid = _config_uid(path, f"/hooks/{event_name}")
        result.nodes.append(
            GraphNode(
                uid=uid,
                kind="event",
                label=event_name,
                file_path=normalised,
                lang="json",
                metadata={"extractor": EXTRACTOR_ID, "subkind": "hook_event"},
            )
        )
        result.edges.append(
            GraphEdge(
                source_uid=file_uid_,
                target_uid=uid,
                edge_type="declares",
                extractor=EXTRACTOR_ID,
                confidence=1.0,
            )
        )


def _detect_subtype(name: str) -> str:
    """Map filename → subtype emitter. Returns 'generic' as default."""
    lname = name.lower()
    if lname == "package.json":
        return "package"
    if lname.endswith("tsconfig.json") or lname == "tsconfig.json":
        return "tsconfig"
    if lname == "mcp.json" or lname == ".mcp.json":
        return "mcp"
    if lname == "settings.json" or (lname.startswith("settings.") and lname.endswith(".json")):
        return "settings"
    return "generic"


# ---------------------------------------------------------------------------
# Public entry
# ---------------------------------------------------------------------------


def extract(path: str, content: str) -> ExtractionResult:
    """Parse a JSON config file → nodes + edges."""
    result = ExtractionResult()
    normalised = _normalize_path(path)
    file_name = PurePosixPath(normalised).name
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]

    file_node = GraphNode(
        uid=file_uid(path),
        kind="code:file",
        label=file_name,
        file_path=normalised,
        lang="json",
        content_hash=content_hash,
        metadata={"extractor": EXTRACTOR_ID},
    )
    result.nodes.append(file_node)

    data, err = _parse_lenient(content)
    if err is not None or data is None:
        result.parse_errors.append(
            ParseError(kind="json_decode", detail=err or "unknown JSON parse failure")
        )
        emit_contains_spine(
            file_path=path,
            file_uid_=file_uid(path),
            result=result,
            extractor_id=EXTRACTOR_ID,
        )
        _promote_stubs(result)
        return result

    subtype = _detect_subtype(file_name)
    if isinstance(data, dict):
        if subtype == "package":
            _emit_package_json(data, path, normalised, file_node.uid, result)
        elif subtype == "tsconfig":
            _emit_tsconfig_json(data, path, normalised, file_node.uid, result)
        elif subtype == "mcp":
            _emit_mcp_json(data, path, normalised, file_node.uid, result)
        elif subtype == "settings":
            _emit_settings_json(data, path, normalised, file_node.uid, result)

    emit_contains_spine(
        file_path=path,
        file_uid_=file_uid(path),
        result=result,
        extractor_id=EXTRACTOR_ID,
    )
    _promote_stubs(result)
    return result


__all__ = ["EXTRACTOR_ID", "extract", "file_uid"]
