"""Cross-repo edge inference (I.12)."""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field

from ..types import EvidenceSignal, GraphEdge
from .manifest import GroupManifest

logger = logging.getLogger("graph_os.groups.cross_repo")

EXTRACTOR_ID = "groups.cross_repo@v1"


@dataclass
class MemberInputs:
    """Normalised per-member contribution to the group."""

    alias: str
    routes: list[dict] = field(default_factory=list)  # {method, path, handler_uid?}
    mcp_tools: list[str] = field(default_factory=list)
    fetches: list[dict] = field(default_factory=list)  # {caller_uid, method, path}


@dataclass
class CrossRepoReport:
    edges: list[GraphEdge] = field(default_factory=list)
    ambiguous_routes: list[str] = field(default_factory=list)
    unresolved_fetches: list[str] = field(default_factory=list)


def infer_cross_repo_edges(
    manifest: GroupManifest,
    inputs: Iterable[MemberInputs],
) -> CrossRepoReport:
    """Build cross-repo edges from per-member extract data."""
    report = CrossRepoReport()

    # Index all routes for quick lookup by (method, path).
    route_index: dict[tuple[str, str], list[tuple[str, dict]]] = defaultdict(list)
    for mi in inputs:
        for route in mi.routes:
            key = (route.get("method", "get").lower(), route.get("path", ""))
            route_index[key].append((mi.alias, route))

    # MCP tool owners.
    tool_owners: dict[str, str] = {}
    for mi in inputs:
        for tool in mi.mcp_tools:
            tool_owners[tool] = mi.alias

    inputs_list = list(inputs)

    for mi in inputs_list:
        for fetch in mi.fetches:
            method = fetch.get("method", "get").lower()
            path = fetch.get("path", "")
            owners = _owning_members(manifest, path)
            candidates = route_index.get((method, path), [])
            if owners:
                # Explicit ownership → confidence 0.95 to declared target.
                for owner_alias in owners:
                    target = next((r for alias, r in candidates if alias == owner_alias), None)
                    if target is None:
                        # Owner declared the route but extractor didn't pick it
                        # up (could be a dynamic route). Still emit a
                        # high-confidence edge to the owner's synthetic uid.
                        target = {
                            "method": method,
                            "path": path,
                            "handler_uid": f"cos:route:{method.upper()}:{path}",
                        }
                    report.edges.append(
                        _build_edge(
                            source_uid=fetch.get("caller_uid", f"code:unknown:{mi.alias}"),
                            target_uid=target.get("handler_uid")
                            or f"cos:route:{method.upper()}:{path}",
                            edge_type="calls_contract",
                            confidence=0.95,
                            evidence=(
                                EvidenceSignal("ownership_declared", 0.55, note=owner_alias),
                                EvidenceSignal("route_match", 0.4),
                            ),
                        )
                    )
                continue

            if candidates:
                # No explicit ownership — inferred link to each plausible owner.
                for alias, target in candidates:
                    if alias == mi.alias:
                        continue  # self-edge — skip
                    report.edges.append(
                        _build_edge(
                            source_uid=fetch.get("caller_uid", f"code:unknown:{mi.alias}"),
                            target_uid=target.get("handler_uid")
                            or f"cos:route:{method.upper()}:{path}",
                            edge_type="calls_contract",
                            confidence=0.6,
                            evidence=(EvidenceSignal("route_match_inferred", 0.6),),
                        )
                    )
                    report.ambiguous_routes.append(path)
            else:
                report.unresolved_fetches.append(path)

    # MCP tool edges — tools are unique strings so confidence 0.95.
    for mi in inputs_list:
        for fetch in mi.mcp_tools:
            # no-op; MCP tool edges are emitted when someone imports
            # `cos_graph_query` etc. — callers supply that in `fetches`
            # with method="mcp". For now the simpler contract:
            if fetch in tool_owners and tool_owners[fetch] != mi.alias:
                report.edges.append(
                    _build_edge(
                        source_uid=f"code:unknown:{mi.alias}",
                        target_uid=f"cos:mcp_tool:{fetch}",
                        edge_type="calls_mcp_tool",
                        confidence=0.95,
                        evidence=(EvidenceSignal("mcp_tool_unique", 0.95),),
                    )
                )

    return report


def _owning_members(manifest: GroupManifest, path: str) -> list[str]:
    return [m.alias for m in manifest.members if m.owns_route(path)]


def _build_edge(
    *,
    source_uid: str,
    target_uid: str,
    edge_type: str,
    confidence: float,
    evidence: tuple[EvidenceSignal, ...] = (),
) -> GraphEdge:
    return GraphEdge(
        source_uid=source_uid,
        target_uid=target_uid,
        edge_type=edge_type,
        extractor=EXTRACTOR_ID,
        confidence=confidence,
        evidence=evidence,
    )


__all__ = [
    "CrossRepoReport",
    "MemberInputs",
    "infer_cross_repo_edges",
]
