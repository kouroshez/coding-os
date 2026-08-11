"""cos_graph_contracts — the API / MCP / event handler surface listing."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from ..backend import BackendUnavailable
from . import graph as _kernel
from .graph import (
    NodeSummary,
    _count_edges_for,
    _fail,
    _normalize_kinds,
    _ok,
)


def _is_test_source(uid: str) -> bool:
    """True when a uid lives under a tests/ tree (R4-10)."""
    return "/tests/" in uid or ":tests/" in uid or "test_" in uid.rsplit("/", 1)[-1]


def cos_graph_contracts(
    *,
    scope: str = "all",
    kinds: Sequence[str] = ("http", "mcp", "grpc", "event", "websocket"),
    include_test_sources: bool = False,
    backend: str | None = None,
) -> dict[str, Any]:
    """API surface — enumerate every route / tool / event handler."""
    try:
        be = _kernel._backend(backend=backend)
    except BackendUnavailable as exc:
        return _fail("unavailable", str(exc), retryable=True)

    # G3: normalize kinds (wire trap)
    parsed_kinds = _normalize_kinds(kinds)
    if not parsed_kinds:
        parsed_kinds = ("http", "mcp", "grpc", "event", "websocket")

    buckets: dict[str, list[dict[str, Any]]] = {
        "http_routes": [],
        "mcp_tools": [],
        "grpc_endpoints": [],
        "event_handlers": [],
        "websocket": [],
    }
    # Per-edge-type slice — silent truncation at limit=2000 would hide
    # contracts on a large API surface. Counter each kind so the agent
    # knows if the slice was complete.
    # G5: was 2000; default invocation blew past MCP token cap (106KB).
    # 200 per-edge-type bucket keeps the typical envelope well under
    # ~10K tokens; callers needing more can paginate.
    _CONTRACT_BUCKET_LIMIT = 200
    per_kind_truncated: dict[str, bool] = {}
    for edge_type in ("handles_route", "handles_tool", "handles_event"):
        edges_slice = be.list_edges(edge_types=(edge_type,), limit=_CONTRACT_BUCKET_LIMIT)
        total = _count_edges_for(be, edge_types=(edge_type,))
        per_kind_truncated[edge_type] = total > len(edges_slice)
        for edge in edges_slice:
            node = be.get_node(edge.target_uid)
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
            bucket_key = {
                "http": "http_routes",
                "mcp": "mcp_tools",
                "grpc": "grpc_endpoints",
                "event": "event_handlers",
                "websocket": "websocket",
            }.get(kind, "http_routes")
            buckets[bucket_key].append(
                {
                    **NodeSummary.from_node(node).to_dict(),
                    "method": (node.metadata or {}).get("method"),
                    "path": (node.metadata or {}).get("path"),
                    "framework": (node.metadata or {}).get("framework"),
                    "handler": (node.metadata or {}).get("handler"),
                    "source": edge.source_uid,
                    "confidence": edge.confidence,
                }
            )

    # W7 / R4-10: dedupe each bucket by target uid, preferring a
    # non-test source; and (unless asked) drop entries whose ONLY source
    # is a test fixture. Pre-fix the same MCP tool appeared once per
    # source file (production + every test that decorated a fake handler).
    def _dedupe_bucket(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        by_uid: dict[str, dict[str, Any]] = {}
        for item in items:
            uid = item.get("uid", "")
            src = item.get("source", "") or ""
            existing = by_uid.get(uid)
            if existing is None:
                by_uid[uid] = item
            elif _is_test_source(existing.get("source", "") or "") and not _is_test_source(src):
                # Replace a test-sourced entry with a production one.
                by_uid[uid] = item
        out = list(by_uid.values())
        if not include_test_sources:
            non_test = [it for it in out if not _is_test_source(it.get("source", "") or "")]
            # Keep test-only contracts only when nothing else defines them.
            if non_test:
                out = non_test
        return out

    buckets = {k: _dedupe_bucket(v) for k, v in buckets.items()}
    result_truncated = any(per_kind_truncated.values())
    return _ok(
        {"scope": scope, **buckets, "count": sum(len(v) for v in buckets.values())},
        meta={
            "backend": be.backend_id,
            "kinds": list(parsed_kinds),
            "bucket_limit": _CONTRACT_BUCKET_LIMIT,
            "result_truncated": result_truncated,
            "per_edge_type_truncated": per_kind_truncated,
            "include_test_sources": include_test_sources,
        },
    )
