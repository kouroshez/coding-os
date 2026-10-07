"""cos_graph_contracts — the API / MCP / event handler surface listing."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from typing import Any

from ..backend import BackendUnavailable
from ..test_paths import is_test_path
from . import graph as _kernel
from .graph import (
    NodeSummary,
    _count_edges_for,
    _fail,
    _normalize_kinds,
    _ok,
)


def _is_test_source(uid: str) -> bool:
    path = uid.split(":", 2)[-1].split("::", 1)[0]
    return is_test_path(path)


def _span(source_span: str | None, node: Any) -> tuple[str | None, int | None]:
    path, _, line = (source_span or "").rpartition(":")
    if path and line.isdigit():
        return path, int(line)
    return node.file_path, node.start_line


def _framework(edge: Any, kind: str) -> str | None:
    # Contracts name each registration's evidence `<framework>_<kind>`.
    suffix = f"_{kind}"
    for signal in edge.evidence or ():
        if signal.signal_name.endswith(suffix):
            return str(signal.signal_name[: -len(suffix)])
    return None


_BUCKET_BY_KIND = {
    "http": "http_routes",
    "mcp": "mcp_tools",
    "grpc": "grpc_endpoints",
    "event": "event_handlers",
    "websocket": "websocket",
}
_CONTRACT_EDGE_TYPES = ("handles_route", "handles_tool", "handles_event")
# One page keeps the default envelope well under ~10K tokens; `offset` reaches the rest.
_CONTRACT_PAGE_LIMIT = 200


def _in_scope(file_path: str | None, scope: str) -> bool:
    prefix = scope.strip().removeprefix("./").rstrip("/")
    if prefix in ("", "all", "."):
        return True
    return bool(file_path) and (file_path == prefix or str(file_path).startswith(prefix + "/"))


def _site_order(item: dict[str, Any]) -> tuple[str, int, str]:
    return item.get("file_path") or "", item.get("start_line") or 0, item.get("uid") or ""


def cos_graph_contracts(
    *,
    scope: str = "all",
    kinds: Sequence[str] = ("http", "mcp", "grpc", "event", "websocket"),
    include_test_sources: bool = False,
    offset: int = 0,
    limit: int = _CONTRACT_PAGE_LIMIT,
    backend: str | None = None,
) -> dict[str, Any]:
    """API surface — enumerate every route / tool / event handler."""
    if limit <= 0:
        return _fail("validation", "limit must be > 0")
    if offset < 0:
        return _fail("validation", "offset must be >= 0")
    try:
        be = _kernel._backend(backend=backend)
    except BackendUnavailable as exc:
        return _fail("unavailable", str(exc), retryable=True)

    # G3: normalize kinds (wire trap)
    parsed_kinds = _normalize_kinds(kinds)
    if not parsed_kinds:
        parsed_kinds = ("http", "mcp", "grpc", "event", "websocket")

    buckets: dict[str, list[dict[str, Any]]] = {key: [] for key in _BUCKET_BY_KIND.values()}
    for edge_type in _CONTRACT_EDGE_TYPES:
        # Every registration is read before the page is cut: a slice of the 200
        # most confident edges showed 1 of 196 Fiber routes.
        total = _count_edges_for(be, edge_types=(edge_type,))
        if not total:
            continue
        edges = be.list_edges(edge_types=(edge_type,), limit=total, include_evidence=True)
        nodes = be.get_nodes_bulk([edge.target_uid for edge in edges])
        for edge in edges:
            node = nodes.get(edge.target_uid)
            if node is None:
                continue
            md = node.metadata or {}
            kind = md.get("kind")
            if kind is None:
                # No contract sub-kind in metadata → infer from the node's
                # own kind. A node that is not a contract surface (e.g. a
                # hook reached via a handles_tool edge) is skipped, not
                # dumped into http_routes via a blind 'http' default.
                node_kind = (node.kind or "").replace("cos:", "")
                kind = {"route": "http", "mcp_tool": "mcp", "cli_command": "cli"}.get(node_kind)
                if kind is None:
                    continue
            if kind not in parsed_kinds:
                continue
            # A route two services both register is one node whose fields name
            # the last writer; each registration's own place is its edge span.
            file_path, line = _span(edge.source_span, node)
            if not _in_scope(file_path, scope):
                continue
            own_site = file_path == node.file_path
            buckets[_BUCKET_BY_KIND.get(kind, "http_routes")].append(
                {
                    **NodeSummary.from_node(node).to_dict(),
                    "file_path": file_path,
                    "start_line": line,
                    "method": md.get("method"),
                    "path": md.get("path"),
                    "framework": md.get("framework") if own_site else _framework(edge, kind),
                    "handler": md.get("handler") if own_site else None,
                    "source": edge.source_uid,
                    "confidence": edge.confidence,
                    "_edge_type": edge_type,
                }
            )

    # Per target uid: keep every production registration, collapse test
    # fixtures to one, and (unless asked) drop contracts only tests define.
    def _dedupe_bucket(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        by_uid: dict[str, list[dict[str, Any]]] = {}
        for item in items:
            by_uid.setdefault(item.get("uid", ""), []).append(item)
        out: list[dict[str, Any]] = []
        for group in by_uid.values():
            # Every production registration stays (two services may serve the
            # same path); test fixtures collapse to one stand-in.
            production = {
                item.get("source", ""): item
                for item in group
                if not _is_test_source(item.get("source", "") or "")
            }
            out.extend(production.values() or group[:1])
        if not include_test_sources:
            non_test = [it for it in out if not _is_test_source(it.get("source", "") or "")]
            # Keep test-only contracts only when nothing else defines them.
            if non_test:
                out = non_test
        return out

    ordered = [
        (key, item)
        for key, items in buckets.items()
        for item in sorted(_dedupe_bucket(items), key=_site_order)
    ]
    page = ordered[offset : offset + limit]
    page_buckets: dict[str, list[dict[str, Any]]] = {key: [] for key in buckets}
    for key, item in page:
        page_buckets[key].append({k: v for k, v in item.items() if k != "_edge_type"})
    shown = Counter(item["_edge_type"] for _, item in page)
    present = Counter(item["_edge_type"] for _, item in ordered)
    return _ok(
        {"scope": scope, **page_buckets, "count": len(page), "total_count": len(ordered)},
        meta={
            "backend": be.backend_id,
            "kinds": list(parsed_kinds),
            "offset": offset,
            "limit": limit,
            "bucket_limit": limit,
            "result_truncated": offset + len(page) < len(ordered),
            "per_edge_type_truncated": {
                edge_type: present[edge_type] > shown[edge_type]
                for edge_type in _CONTRACT_EDGE_TYPES
            },
            "include_test_sources": include_test_sources,
        },
    )
