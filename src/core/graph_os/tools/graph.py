"""graph_os — the 11 cos_graph_* MCP tools (I.8).

DEPENDS:  graph_os.types, graph_os.backend, graph_os.backends.*.
"""

from __future__ import annotations

import difflib
import logging
import os
import re
import sys
import threading
from collections import deque
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..backend import BackendUnavailable, GraphBackend, get_backend
from ..types import GraphEdge, GraphNode

logger = logging.getLogger("graph_os.tools.graph")


# ---------------------------------------------------------------------------
# Envelope helpers — shared with thinking_os via sys.path.
# ---------------------------------------------------------------------------


def _envelope_module():
    try:
        from tools import _shared  # type: ignore

        return _shared
    except ImportError:
        here = Path(__file__).resolve()
        candidate = here.parent.parent.parent / "thinking_os"
        if candidate.exists() and str(candidate) not in sys.path:
            sys.path.insert(0, str(candidate))
        from tools import _shared  # type: ignore

        return _shared


def _ok(data: dict[str, Any], meta: dict[str, Any] | None = None) -> dict[str, Any]:
    shared = _envelope_module()
    merged = {"layer": "graph", **(meta or {})}
    _emit_telemetry(meta=merged, ok=True)
    _touch_session_marker()
    return shared.ok(data, meta=merged)


def _touch_session_marker() -> None:
    """Record that a cos_graph_* call succeeded this agent session.

    Consumed by enforce-graph-first-read.sh — when the marker exists,
    the hook stays silent on Read. Fail-open: any error is logged at
    debug level only, never raises.
    """
    try:
        agent_dir = os.environ.get("COS_AGENT_DIR")
        if not agent_dir:
            state_dir = os.environ.get("COS_STATE_DIR") or ".coding-os"
            agent = os.environ.get("COS_AGENT") or "claude"
            agent_dir = f"{state_dir}/{agent}"
        from pathlib import Path as _Path

        path = _Path(agent_dir)
        path.mkdir(parents=True, exist_ok=True)
        (path / ".graph-call-seen").touch(exist_ok=True)
    except OSError as exc:
        logger.debug("graph-call-seen marker failed: %s", exc)


def _fail(
    category: str,
    message: str,
    *,
    retryable: bool | None = None,
) -> dict[str, Any]:
    shared = _envelope_module()
    _emit_telemetry(
        meta={"layer": "graph", "category": category, "message": message},
        ok=False,
    )
    return shared.fail(category, message, retryable=retryable)


# -- Telemetry --------------------------------------------------------
# Append-only JSONL log of every cos_graph_* invocation. One line per
# call: {ts, ok, layer, source, backend, ...meta}. The file lives in
# $COS_STATE_DIR/.graph-telemetry.jsonl and is rotated when it crosses
# a soft cap so the disk footprint stays bounded.

_TELEMETRY_MAX_BYTES = 2 * 1024 * 1024  # 2 MB
_TELEMETRY_PATH_CACHE: list[str] = []


def _telemetry_path() -> str | None:
    if _TELEMETRY_PATH_CACHE:
        return _TELEMETRY_PATH_CACHE[0]
    state_dir = os.environ.get("COS_STATE_DIR")
    if not state_dir:
        # Fall back to repo-rooted .coding-os when env unset.
        from pathlib import Path as _Path

        state_dir = str(_Path.cwd() / ".coding-os")
    try:
        from pathlib import Path as _Path

        path = _Path(state_dir)
        path.mkdir(parents=True, exist_ok=True)
        full = str(path / ".graph-telemetry.jsonl")
        _TELEMETRY_PATH_CACHE.append(full)
        return full
    except OSError as exc:
        logger.debug("telemetry path setup failed: %s", exc)
        return None


def _rotate_telemetry_atomically(path: str) -> None:
    try:
        size = os.path.getsize(path)
    except OSError:
        return
    if size <= _TELEMETRY_MAX_BYTES:
        return
    tmp = f"{path}.rotating"
    try:
        with open(path, "rb") as src:
            src.seek(size // 2)
            tail = src.read()
        with open(tmp, "wb") as dst:
            dst.write(tail)
        os.replace(tmp, path)
    except OSError as exc:
        logger.debug("telemetry rotation skipped: %s", exc)
        try:
            os.unlink(tmp)
        except OSError:
            pass


def _emit_telemetry(*, meta: dict[str, Any], ok: bool) -> None:
    """Append one JSONL row. Fail-open — telemetry must never block a tool."""
    try:
        path = _telemetry_path()
        if path is None:
            return
        import json as _json
        import time as _time

        row = {
            "ts": int(_time.time()),
            "ok": ok,
            **{k: v for k, v in meta.items() if isinstance(v, (str, int, float, bool))},
        }
        line = _json.dumps(row, default=str) + "\n"
        _rotate_telemetry_atomically(path)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(line)
    except Exception as exc:
        logger.debug("telemetry emit suppressed: %s", exc)


# ---------------------------------------------------------------------------
# Backend handle — lazy, shared, re-openable.
# ---------------------------------------------------------------------------


# Legacy single-instance singleton — kept as a test-override seam.  Tests
# in core/graph_os/tests/ monkey-patch this directly to inject a stub
# backend; the new project-scoped dict below takes precedence ONLY when
# this legacy slot is None.  Production callers (MCP, Hub web) never
# write to `_BACKEND_SINGLETON` so the project-scoped path always wins.
_BACKEND_SINGLETON: GraphBackend | None = None
_BACKEND_SINGLETONS: dict[str, GraphBackend] = {}
_BACKEND_LOCK = threading.Lock()


def _current_db_key() -> str:
    """Resolve the SQLite DB path for the current project scope."""
    try:
        from thinking_os.database import resolve_db_path  # type: ignore

        return str(resolve_db_path())
    except Exception:
        return "__default__"


def _repo_root_for_paths() -> Path:
    """Project root used to resolve relative file_path entries against the
    filesystem (e.g. stale-path detection in cos_graph_doctor).

    The DB lives at ``<repo>/.coding-os/coding-os.db``, so we walk two
    parents up. Falls back to CWD if the DB path can't be resolved.
    """
    try:
        from thinking_os.database import resolve_db_path  # type: ignore

        db = Path(resolve_db_path()).resolve()
        return db.parent.parent
    except Exception:
        return Path.cwd().resolve()


def _backend(*, backend: str | None = None) -> GraphBackend:
    """Return the shared GraphBackend instance for the active project scope.

    Lookup order:
      1. ``_BACKEND_SINGLETON`` legacy slot — non-None only when a test
         has installed a stub backend via direct module-attr assignment.
      2. ``_BACKEND_SINGLETONS[db_path]`` — production path.  Keyed by
         resolved SQLite DB path so the Hub web layer can serve many
         projects from one process without one project leaking into
         another's response.  MCP / CLI callers see exactly one entry
         and behave as before.

    B7: close the previous backend before replacing the singleton when the
    caller asks for a different backend, so file handles / DB connections
    don't leak across the swap. Lock guards against concurrent callers
    swapping the singleton mid-call.
    """
    with _BACKEND_LOCK:
        if _BACKEND_SINGLETON is not None and backend is None:
            return _BACKEND_SINGLETON
        key = _current_db_key()
        existing = _BACKEND_SINGLETONS.get(key)
        if existing is None or backend is not None:
            if existing is not None:
                try:
                    existing.close()
                except Exception as exc:
                    logger.debug("previous backend close suppressed: %s", exc)
            new_backend = get_backend(backend=backend)
            _BACKEND_SINGLETONS[key] = new_backend
            return new_backend
        return existing


def reset_backend() -> None:
    """Test-only: drop both legacy + project-scoped caches."""
    global _BACKEND_SINGLETON
    with _BACKEND_LOCK:
        if _BACKEND_SINGLETON is not None:
            try:
                _BACKEND_SINGLETON.close()
            except Exception as exc:
                logger.debug("legacy backend close suppressed: %s", exc)
            _BACKEND_SINGLETON = None
        for bk in list(_BACKEND_SINGLETONS.values()):
            try:
                bk.close()
            except Exception as exc:
                logger.debug("reset_backend close suppressed: %s", exc)
        _BACKEND_SINGLETONS.clear()


# ---------------------------------------------------------------------------
# UID resolution
# ---------------------------------------------------------------------------
#
# Tools accept fully-qualified node uids ("code:file:foo.py",
# "code:function:foo.py::bar", "doc:file:README.md", "folder:src/utils").
# Agents (and humans) often pass a raw repo path because that is the most
# natural mental model. _resolve_uid bridges the gap by transparently
# retrying a small set of well-known prefixes when the literal lookup
# misses, and _fail_uid_not_found returns the candidates tried plus a
# scheme cheat-sheet so failures are self-explanatory.

_UID_PATH_PREFIXES: tuple[str, ...] = (
    "code:file:",
    "doc:file:",
    "folder:",
)

_UID_FORMAT_HINT = (
    "uids follow the scheme code:file:<path> | "
    "code:function:<path>::<name> | code:class:<path>::<name> | "
    "code:module:<dotted> | doc:file:<path> | "
    "doc:heading:<path>#<slug>:<level> | folder:<path>. "
    "Use cos_graph_query to discover candidates."
)


def _looks_prefixed(raw: str) -> bool:
    """True when input already carries an explicit uid scheme."""
    head = raw.split("/", 1)[0]
    return ":" in head


def _resolve_uid(backend: GraphBackend, raw_uid: str) -> tuple[GraphNode | None, list[str]]:
    """Look up a node uid, with path-prefix fallback for raw paths.

    Returns ``(node, tried)`` where ``tried`` is the ordered list of uid
    candidates we attempted. The first entry is always the literal input
    so error messages can reflect the user's original intent.
    """
    direct = backend.get_node(raw_uid)
    if direct is not None:
        return direct, [raw_uid]

    if _looks_prefixed(raw_uid):
        return None, [raw_uid]

    tried: list[str] = [raw_uid]
    for prefix in _UID_PATH_PREFIXES:
        candidate = f"{prefix}{raw_uid}"
        tried.append(candidate)
        node = backend.get_node(candidate)
        if node is not None:
            return node, tried
    return None, tried


def _fail_uid_not_found(
    raw_uid: str,
    tried: list[str],
    *,
    label: str = "uid",
) -> dict[str, Any]:
    """Helpful 'not_found' envelope including the candidates tried."""
    if len(tried) > 1:
        suggestions = ", ".join(repr(c) for c in tried[1:])
        msg = f"no node with {label} {raw_uid!r} (also tried {suggestions}). {_UID_FORMAT_HINT}"
    else:
        msg = f"no node with {label} {raw_uid!r}. {_UID_FORMAT_HINT}"
    return _fail("not_found", msg)


# ---------------------------------------------------------------------------
# Shared retrieval helpers
# ---------------------------------------------------------------------------


@dataclass
class NodeSummary:
    uid: str
    kind: str
    label: str
    file_path: str | None
    start_line: int | None
    # Optional centrality / hub score, populated by exporters that
    # have a degree map handy (graph_export, graph_query). None when
    # the caller did not pre-compute degrees.
    degree: int | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "uid": self.uid,
            "kind": self.kind,
            "label": self.label,
            "file_path": self.file_path,
            "start_line": self.start_line,
        }
        if self.degree is not None:
            out["degree"] = self.degree
        return out

    @classmethod
    def from_node(cls, node: GraphNode, *, degree: int | None = None) -> NodeSummary:
        return cls(
            uid=node.uid,
            kind=node.kind,
            label=node.label,
            file_path=node.file_path,
            start_line=node.start_line,
            degree=degree,
        )


def _degree_map_for(backend: GraphBackend, uids: Sequence[str]) -> dict[str, int]:
    """Server-side degree count for a node set.

    Cheaper than the client recomputing on every render: one query per
    export instead of N. Falls back to {} when the backend is not
    SQLite-backed (Kuzu can extend later) so consumers can degrade
    gracefully.
    """
    if not uids:
        return {}
    sqlite_conn = getattr(backend, "_conn", None)
    if sqlite_conn is None:
        return {}
    placeholders = ",".join("?" * len(uids))
    try:
        rows = sqlite_conn.execute(
            f"""
            SELECT n.uid, COUNT(*)
            FROM graph_edges_v12 e
            JOIN graph_nodes n ON n.id = e.source_id OR n.id = e.target_id
            WHERE n.uid IN ({placeholders})
            GROUP BY n.uid
            """,
            tuple(uids),
        ).fetchall()
    except Exception as exc:
        logger.debug("degree query suppressed: %s", exc)
        return {}
    return {row[0]: int(row[1]) for row in rows}


def _edge_to_dict(edge: GraphEdge, *, include_evidence: bool = False) -> dict[str, Any]:
    # TASK-122: surface provenance derived from extractor — additive,
    # never replaces the existing extractor field.  Hub UI consumers
    # (ImpactPanel, ContextPanel) can colour or filter by this label
    # without parsing extractor IDs.
    from ..types import provenance_for

    out: dict[str, Any] = {
        "source_uid": edge.source_uid,
        "target_uid": edge.target_uid,
        "edge_type": edge.edge_type,
        "confidence": edge.confidence,
        "extractor": edge.extractor,
        "provenance": provenance_for(edge.extractor),
        "source_span": edge.source_span,
    }
    if include_evidence:
        out["evidence"] = [
            {"signal_name": s.signal_name, "weight": s.weight, "note": s.note}
            for s in edge.evidence
        ]
    return out


def _walk_bfs(
    backend: GraphBackend,
    *,
    root_uid: str,
    direction: str,
    max_hops: int,
    confidence_min: float,
    edge_types: Sequence[str] | None,
    visit_limit: int = 500,
) -> tuple[list[GraphNode], list[GraphEdge]]:
    """BFS traversal — shared by context / impact / trace.

    direction: "out" (source→target), "in" (target→source), or "both".

    B2: edges are only recorded the first time they lead to an unseen
    neighbour — this stops duplicate edges piling up when a neighbour is
    reached through multiple predecessors. Edges already traversed from
    either direction via the (source, target, edge_type, extractor)
    identity are suppressed.
    B6: uses ``get_nodes_bulk`` on the frontier instead of one get_node
    per neighbour, collapsing the N+1 pattern.
    """
    edges_out: list[GraphEdge] = []
    seen_edge_ids: set[tuple[str, str, str, str]] = set()
    root_nodes = _bulk_nodes(backend, [root_uid])
    root_node = root_nodes.get(root_uid)
    if root_node is None:
        return [], []

    seen_nodes: dict[str, GraphNode] = {root_uid: root_node}
    visited_uids: set[str] = {root_uid}
    queue: deque[tuple[str, int]] = deque([(root_uid, 0)])

    while queue and len(seen_nodes) < visit_limit:
        uid, depth = queue.popleft()
        if depth >= max_hops:
            continue
        neighbours: list[GraphEdge] = []
        if direction in ("out", "both"):
            neighbours.extend(
                backend.list_edges(
                    source_uid=uid,
                    edge_types=edge_types,
                    confidence_min=confidence_min,
                    limit=visit_limit,
                )
            )
        if direction in ("in", "both"):
            neighbours.extend(
                backend.list_edges(
                    target_uid=uid,
                    edge_types=edge_types,
                    confidence_min=confidence_min,
                    limit=visit_limit,
                )
            )

        frontier_uids: list[str] = []
        frontier_edges: list[GraphEdge] = []
        for edge in neighbours:
            identity = (
                edge.source_uid,
                edge.target_uid,
                edge.edge_type,
                edge.extractor,
            )
            if identity in seen_edge_ids:
                continue
            seen_edge_ids.add(identity)
            next_uid = edge.target_uid if edge.source_uid == uid else edge.source_uid
            # B2: only append when the neighbour is new — stops the edge
            # duplication that happened when the same node was reached
            # via multiple edges from different frontiers.
            if next_uid in visited_uids:
                continue
            frontier_edges.append(edge)
            frontier_uids.append(next_uid)

        if frontier_uids:
            fetched = _bulk_nodes(backend, frontier_uids)
            for edge, next_uid in zip(frontier_edges, frontier_uids):
                node = fetched.get(next_uid)
                if node is None:
                    continue
                edges_out.append(edge)
                if next_uid in visited_uids:
                    continue
                visited_uids.add(next_uid)
                seen_nodes[next_uid] = node
                queue.append((next_uid, depth + 1))
    return list(seen_nodes.values()), edges_out


def _contains_ancestors(
    backend: GraphBackend,
    *,
    leaf_uid: str,
    max_hops: int = 16,
) -> tuple[list[GraphNode], list[GraphEdge]]:
    """Walk the CONTAINS spine from ``leaf_uid`` up to the repo root."""
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []
    seen: set[str] = {leaf_uid}
    current = leaf_uid
    for _ in range(max_hops):
        inbound = backend.list_edges(
            target_uid=current,
            edge_types=("contains",),
            limit=50,
        )
        if not inbound:
            break
        # Pick the first stable parent — spine edges are 1:N on outbound
        # but 1:1 on inbound once de-duplicated; iterate until we find
        # one we haven't visited.
        parent_edge = None
        for edge in inbound:
            if edge.source_uid not in seen:
                parent_edge = edge
                break
        if parent_edge is None:
            break
        parent_uid = parent_edge.source_uid
        seen.add(parent_uid)
        parent_node = backend.get_node(parent_uid)
        if parent_node is None:
            break
        nodes.append(parent_node)
        edges.append(parent_edge)
        current = parent_uid
        if parent_uid == "folder:.":
            break
    # Return root → leaf order so the caller can render breadcrumbs
    # left-to-right.
    nodes.reverse()
    edges.reverse()
    return nodes, edges


def _bulk_nodes(backend: GraphBackend, uids: Sequence[str]) -> dict[str, GraphNode]:
    """B6: prefer backend.get_nodes_bulk; fall back to per-uid for legacy."""
    bulk = getattr(backend, "get_nodes_bulk", None)
    if callable(bulk):
        return bulk(list(uids))
    out: dict[str, GraphNode] = {}
    for uid in uids:
        node = backend.get_node(uid)
        if node is not None:
            out[uid] = node
    return out


# ---------------------------------------------------------------------------
# The 11 tools
# ---------------------------------------------------------------------------


def cos_graph_query(
    q: str,
    *,
    kinds: Sequence[str] | None = None,
    limit: int = 10,
    max_hops: int = 2,
    confidence_min: float = 0.3,
    include_spine: bool = False,
    backend: str | None = None,
) -> dict[str, Any]:
    """Hybrid search over node labels + docstrings.

    DEPENDS:      GraphBackend.
    """
    if (not q or not q.strip()) and not kinds:
        return _fail(
            "validation", "query must be a non-empty string (or provide kinds for kind-only browse)"
        )
    try:
        be = _backend(backend=backend)
    except BackendUnavailable as exc:
        return _fail("unavailable", str(exc), retryable=True)

    kinds_filter = tuple(kinds) if kinds else None
    nodes = _lexical_search(be, q=q, kinds=kinds_filter, limit=limit, max_hops=max_hops)

    # Fallback — when lexical hybrid returns nothing AND the query
    # *looks* like a path or uid, try _resolve_uid so agents who pass
    # "adapters/claude/sdk_dispatcher.py" or "ClaudeSDKDispatcher.dispatch"
    # get a hit instead of an empty list. Cheap (one DB lookup) and
    # additive — successful searches are untouched. Kind filter still
    # applies: if the resolved node's kind isn't allowed, skip the
    # fallback so behaviour matches the no-fallback path.
    if not nodes and q and q.strip():
        candidate = q.strip()
        looks_pathlike = (
            "/" in candidate
            or "::" in candidate
            or candidate.endswith((".py", ".ts", ".tsx", ".sh", ".md", ".yaml"))
            or _looks_prefixed(candidate)
        )
        if looks_pathlike:
            resolved, _tried = _resolve_uid(be, candidate)
            if resolved is not None and (kinds_filter is None or resolved.kind in kinds_filter):
                nodes = [resolved]

    results = [
        {
            **NodeSummary.from_node(n).to_dict(),
            "confidence": 1.0,
        }
        for n in nodes
    ]
    # S3: when include_spine is set, attach a ``spine`` list per result
    # — the CONTAINS-ancestor chain from repo-root down to the result.
    if include_spine:
        for result_dict, node in zip(results, nodes):
            ancestors, _ = _contains_ancestors(be, leaf_uid=node.uid)
            result_dict["spine"] = [NodeSummary.from_node(a).to_dict() for a in ancestors]
    # B22: cap meta.query to 500 chars with ellipsis suffix so the
    # envelope stays bounded regardless of how long the query string is.
    _MAX_QUERY_META = 500
    query_meta = q if len(q) <= _MAX_QUERY_META else q[:_MAX_QUERY_META] + "..."

    # TASK-075: process grouping.  Group hit uids by Louvain community
    # so the Search tab can render `LoginFlow` / `RegistrationFlow`
    # buckets.  Communities are computed lazily per backend with a
    # cheap edge-count signature; queries with no clustering signal
    # see an empty `processes` list and the UI falls back to flat.
    processes: list[dict[str, Any]] = []
    try:
        from .. import communities as comm_mod

        all_communities, _membership = comm_mod.compute_communities(be)
        relevant_uids = {n.uid for n in nodes}
        processes = comm_mod.communities_to_processes(all_communities, relevant_uids=relevant_uids)
    except Exception as exc:
        logger.debug("community grouping suppressed: %s", exc)
        processes = []

    return _ok(
        {"results": results[:limit], "processes": processes},
        meta={
            "query": query_meta,
            "backend": be.backend_id,
            "include_spine": include_spine,
            "process_count": len(processes),
        },
    )


def cos_graph_context(
    uid_or_name: str,
    *,
    direction: str = "both",
    depth: int = 1,
    include_content: bool = False,
    include_evidence: bool = False,
    include_spine: bool = False,
    backend: str | None = None,
) -> dict[str, Any]:
    """Neighbourhood around a node."""
    try:
        be = _backend(backend=backend)
    except BackendUnavailable as exc:
        return _fail("unavailable", str(exc), retryable=True)

    root, tried_uids = _resolve_uid(be, uid_or_name)
    if root is None:
        root = _fuzzy_resolve(be, uid_or_name)
    if root is None:
        return _fail_uid_not_found(uid_or_name, tried_uids, label="uid_or_name")

    nodes, edges = _walk_bfs(
        be,
        root_uid=root.uid,
        direction=direction,
        max_hops=max(1, int(depth)),
        confidence_min=0.0,
        edge_types=None,
    )
    # Group neighbours by edge_type for the SPA inspector. Each entry
    # carries the *other endpoint*'s summary (uid / kind / label) plus
    # the edge_type so the panel can render "contains → file.py" rows.
    # Edge metadata (confidence / provenance / evidence) is folded in
    # for callers that want it; the frontend only reads uid/kind/label.
    nodes_by_uid = {n.uid: n for n in nodes}
    nodes_by_uid[root.uid] = root
    grouped: dict[str, list[dict[str, Any]]] = {}
    for e in edges:
        # Pick the endpoint that isn't the root we queried; falls back
        # to target on self-edges so the panel still has a row.
        other_uid = e.target_uid if e.source_uid == root.uid else e.source_uid
        other = nodes_by_uid.get(other_uid)
        if other is None:
            continue
        entry: dict[str, Any] = {
            "uid": other.uid,
            "kind": other.kind,
            "label": other.label,
            "edge_type": e.edge_type,
            "confidence": e.confidence,
            "extractor": e.extractor,
        }
        if include_evidence and e.evidence:
            entry["evidence"] = [
                {"signal_name": s.signal_name, "weight": s.weight, "note": s.note}
                for s in e.evidence
            ]
        grouped.setdefault(e.edge_type, []).append(entry)

    # B21: include source content for each node when requested.
    def _node_dict(node: GraphNode) -> dict[str, Any]:
        d = NodeSummary.from_node(node).to_dict()
        if include_content:
            snippet = _read_node_content(node)
            if snippet is not None:
                d["content"] = snippet["content"]
                d["truncated"] = snippet["truncated"]
        return d

    payload: dict[str, Any] = {
        "node": _node_dict(root),
        "neighbours": [_node_dict(n) for n in nodes if n.uid != root.uid],
        "edges_by_type": grouped,
        "edge_count": len(edges),
    }
    if include_spine:
        # S3: surface the CONTAINS-ancestor chain (repo-root → … → leaf)
        # so the SPA can render breadcrumbs alongside the context view.
        ancestors, spine_edges = _contains_ancestors(be, leaf_uid=root.uid)
        payload["spine"] = [NodeSummary.from_node(a).to_dict() for a in ancestors]
        payload["spine_edges"] = [_edge_to_dict(e) for e in spine_edges]
    return _ok(
        payload,
        meta={
            "backend": be.backend_id,
            "depth": depth,
            "direction": direction,
            "include_spine": include_spine,
        },
    )


def cos_graph_impact(
    uid: str,
    *,
    direction: str = "downstream",
    depth: int = 3,
    confidence_min: float = 0.5,
    visit_limit: int = 500,
    backend: str | None = None,
) -> dict[str, Any]:
    """Blast-radius: which nodes depend on (or are depended on by) `uid`.

    Direction semantics (B12):
      "downstream" — nodes that DEPEND ON `uid` (inbound edges from
                     their perspective, i.e. direction="in" in BFS).
                     These are the nodes that WILL BREAK if `uid`
                     changes. Example: callers of a function.

      "upstream"   — nodes that `uid` DEPENDS ON (outbound edges from
                     `uid`'s perspective, i.e. direction="out" in BFS).
                     These are the nodes `uid` CALLS / IMPORTS. Changes
                     to upstream nodes may require `uid` to adapt.
                     Example: libraries or helpers that `uid` imports.

      "both"       — walks in both directions simultaneously.

    DEPRECATION NOTE: the string "downstream" / "upstream" naming
      matches the semantic intent (downstream = consumers, upstream =
      dependencies). The legacy mapping to BFS direction is preserved
      exactly. Do NOT pass raw BFS direction strings ("in"/"out") to
      this parameter — they are unsupported and will default to "in".
    """
    try:
        be = _backend(backend=backend)
    except BackendUnavailable as exc:
        return _fail("unavailable", str(exc), retryable=True)
    root, tried_uids = _resolve_uid(be, uid)
    if root is None:
        return _fail_uid_not_found(uid, tried_uids)

    walk_direction = {"downstream": "in", "upstream": "out", "both": "both"}.get(direction, "in")
    visit_limit = max(1, min(int(visit_limit), 50_000))
    nodes, edges = _walk_bfs(
        be,
        root_uid=root.uid,
        direction=walk_direction,
        max_hops=max(1, int(depth)),
        confidence_min=confidence_min,
        edge_types=None,
        visit_limit=visit_limit,
    )
    # BFS stops once `len(seen_nodes) >= visit_limit`. When it hits the
    # cap the answer is incomplete and silent — agent could mis-judge
    # blast radius. Expose the signal so callers re-run with a smaller
    # depth (typical fix) or raise visit_limit deliberately.
    truncated = len(nodes) >= visit_limit
    tiers: dict[str, list[dict[str, Any]]] = {
        "will_break": [],
        "should_review": [],
        "context": [],
    }
    for edge in edges:
        bucket = (
            "will_break"
            if edge.confidence >= 0.9
            else ("should_review" if edge.confidence >= 0.5 else "context")
        )
        tiers[bucket].append(_edge_to_dict(edge))

    return _ok(
        {
            "root": NodeSummary.from_node(root).to_dict(),
            "direction": direction,
            "tiers": tiers,
            "impacted_count": max(0, len(nodes) - 1),
        },
        meta={
            "backend": be.backend_id,
            "depth": depth,
            "confidence_min": confidence_min,
            "visit_limit": visit_limit,
            "truncated": truncated,
        },
    )


def cos_graph_detect_changes(
    *,
    scope: str = "working",
    files: Sequence[str] | None = None,
    analyze_downstream: bool = True,
    backend: str | None = None,
) -> dict[str, Any]:
    """Pre-commit self-review: map changed files to affected graph nodes."""
    if not files:
        return _ok(
            {
                "scope": scope,
                "files": [],
                "symbols": [],
                "downstream_tasks": [],
                "risk_level": "none",
            },
            meta={"reason": "no files provided"},
        )
    try:
        be = _backend(backend=backend)
    except BackendUnavailable as exc:
        return _fail("unavailable", str(exc), retryable=True)

    affected_symbols: list[dict[str, Any]] = []
    downstream_tasks: set[str] = set()
    risk = "low"

    for file_path in files:
        file_uid = f"code:file:{file_path}"
        node = be.get_node(file_uid)
        if node is None:
            continue
        _, edges = _walk_bfs(
            be,
            root_uid=file_uid,
            direction="both",
            max_hops=1,
            confidence_min=0.0,
            edge_types=None,
        )
        for edge in edges:
            affected_symbols.append(
                {
                    "file": file_path,
                    "source": edge.source_uid,
                    "target": edge.target_uid,
                    "edge_type": edge.edge_type,
                }
            )
            # B15: collect task uids from both the 1-hop walk and, below,
            # the deep walk (depth 3, confidence >= 0.6).
            for uid_candidate in (edge.source_uid, edge.target_uid):
                if uid_candidate.startswith("task:file:"):
                    downstream_tasks.add(uid_candidate)
        if analyze_downstream:
            _, deep_edges = _walk_bfs(
                be,
                root_uid=file_uid,
                direction="in",
                max_hops=3,
                confidence_min=0.6,
                edge_types=None,
            )
            # B15: also collect task uids from the deep (depth-3) walk.
            for deep_edge in deep_edges:
                for uid_candidate in (deep_edge.source_uid, deep_edge.target_uid):
                    if uid_candidate.startswith("task:file:"):
                        downstream_tasks.add(uid_candidate)
            if len(deep_edges) > 20:
                risk = "high"
            elif len(deep_edges) > 5 and risk != "high":
                risk = "medium"

    return _ok(
        {
            "scope": scope,
            "files": list(files),
            "symbols": affected_symbols,
            "downstream_tasks": sorted(downstream_tasks),
            "risk_level": risk,
        },
        meta={"backend": be.backend_id, "analyze_downstream": analyze_downstream},
    )


def cos_graph_trace(
    entry_uid: str,
    *,
    terminals: Sequence[str] = ("return", "exception"),
    max_steps: int = 50,
    backend: str | None = None,
) -> dict[str, Any]:
    """Forward execution walk from an entry point."""
    try:
        be = _backend(backend=backend)
    except BackendUnavailable as exc:
        return _fail("unavailable", str(exc), retryable=True)
    root, tried_entry_uids = _resolve_uid(be, entry_uid)
    start_source = "explicit"
    if root is None:
        # TASK-081: fall back to the highest-scoring entry point whose
        # label / file matches the supplied identifier.  Lets agents
        # call cos_graph_trace("login") without first running a
        # separate query to resolve the uid. The entry_points module
        # is part of an in-flight TASK; tolerate its absence so the
        # tool still returns a useful not_found instead of crashing.
        try:
            from .. import entry_points as ep_mod  # type: ignore[attr-defined]

            ep = ep_mod.best_start_for_query(be, entry_uid)
            if ep is not None:
                root = be.get_node(ep.uid)
                start_source = "entry-point-heuristic"
        except ImportError as exc:
            logger.debug("entry_points fallback unavailable: %s", exc)
    if root is None:
        return _fail_uid_not_found(entry_uid, tried_entry_uids, label="entry_uid")

    steps: list[dict[str, Any]] = []
    branches: list[dict[str, Any]] = []
    seen: set[str] = set()
    stack: list[str] = [root.uid]
    while stack and len(steps) < max_steps:
        uid = stack.pop()
        if uid in seen:
            continue
        seen.add(uid)
        node = be.get_node(uid)
        if node is None:
            continue
        steps.append(NodeSummary.from_node(node).to_dict())
        # B3: follow a wider set of outgoing control-flow edges so traces
        # cover API routes, MCP tool dispatch, event handlers, and async
        # awaits — not just direct calls/constructs.
        edges = be.list_edges(
            source_uid=uid,
            edge_types=(
                "calls",
                "constructs",
                "handles_route",
                "handles_tool",
                "handles_event",
                "dispatches",
                "awaits",
            ),
            limit=20,
        )
        if len(edges) > 1:
            branches.append(
                {
                    "from": uid,
                    "fan_out": [e.target_uid for e in edges],
                }
            )
        for edge in edges:
            if edge.target_uid not in seen:
                stack.append(edge.target_uid)
    return _ok(
        {
            "entry": NodeSummary.from_node(root).to_dict(),
            "steps": steps,
            "branches": branches,
            "terminals": list(terminals),
            "start_source": start_source,
        },
        meta={
            "backend": be.backend_id,
            "step_count": len(steps),
            "start_source": start_source,
        },
    )


def cos_graph_similar(
    uid: str,
    *,
    top_k: int = 5,
    confidence_min: float = 0.5,
    backend: str | None = None,
) -> dict[str, Any]:
    """Semantic similarity — I.8 baseline uses string similarity between
    labels + docstrings; I.1 BGE-M3 embeddings lift the signal later.

    B13: uses ``sample_nodes(kind, limit)`` to build a candidate pool
    from actual graph nodes of the same kind, rather than edge-endpoint
    sampling. Edge-endpoint sampling biases toward high-degree nodes;
    ``sample_nodes`` gives an unbiased draw over the node table.
    """
    try:
        be = _backend(backend=backend)
    except BackendUnavailable as exc:
        return _fail("unavailable", str(exc), retryable=True)
    root, tried_uids = _resolve_uid(be, uid)
    if root is None:
        return _fail_uid_not_found(uid, tried_uids)

    # B13: use sample_nodes for an unbiased candidate pool.
    sample_size = 200  # bounded to keep latency predictable
    sampler = getattr(be, "sample_nodes", None)
    if callable(sampler):
        raw_candidates = sampler(root.kind or None, sample_size)
    else:
        # Graceful degradation for backends that have not yet implemented
        # sample_nodes (should not happen post-S2, but kept for safety).
        raw_candidates = []
        seen_fallback: set[str] = set()
        for edge in be.list_edges(limit=sample_size):
            for side in (edge.source_uid, edge.target_uid):
                if side in seen_fallback:
                    continue
                seen_fallback.add(side)
                n = be.get_node(side)
                if n is not None:
                    raw_candidates.append(n)

    candidates = [n for n in raw_candidates if n.uid != uid]

    # Phase I.1 — use BGE-M3 embeddings when the model is available;
    # fall back to lexical SequenceMatcher otherwise. Both signals get
    # combined linearly so partially-loaded environments still rank.
    scorer_name = "difflib-baseline"
    embed_scores: dict[str, float] = {}
    try:
        from thinking_os.embeddings import (  # type: ignore
            cosine_similarity,
            embed_text,
            is_available,
        )

        if is_available():
            ref_text = (f"{root.label or ''} {root.signature or ''} {root.doc_blob or ''}").strip()
            ref_vec = embed_text(ref_text)
            if ref_vec:
                cand_texts = [
                    f"{n.label or ''} {n.signature or ''} {n.doc_blob or ''}".strip()
                    for n in candidates
                ]
                # batch encode candidate side, then cosine in one shot
                cand_vecs: list[bytes | None] = [embed_text(t) for t in cand_texts]
                valid = [v for v in cand_vecs if v]
                if valid:
                    sims = cosine_similarity(ref_vec, valid)
                    valid_iter = iter(sims)
                    for n, vec in zip(candidates, cand_vecs):
                        if vec is not None:
                            embed_scores[n.uid] = float(next(valid_iter))
                    scorer_name = "bge-m3+difflib-blend"
    except ImportError as exc:
        logger.debug("embeddings module unavailable: %s", exc)
    except Exception as exc:
        logger.debug("embedding similarity skipped: %s", exc)

    scored = []
    reference = f"{root.label or ''} {root.signature or ''} {root.doc_blob or ''}"
    for node in candidates:
        other = f"{node.label or ''} {node.signature or ''} {node.doc_blob or ''}"
        lex = difflib.SequenceMatcher(None, reference, other).ratio()
        emb = embed_scores.get(node.uid)
        # Linear blend: 70% embedding, 30% lexical when embedding ran;
        # 100% lexical otherwise. Keeps results deterministic and lets
        # cold-start environments still answer.
        ratio = (0.7 * emb + 0.3 * lex) if emb is not None else lex
        if ratio >= confidence_min:
            scored.append((ratio, node))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    results = [
        {**NodeSummary.from_node(n).to_dict(), "similarity": round(r, 4)}
        for r, n in scored[: max(1, top_k)]
    ]
    return _ok(
        {"root": NodeSummary.from_node(root).to_dict(), "results": results},
        meta={"backend": be.backend_id, "scorer": scorer_name},
    )


def cos_graph_references(
    uid: str,
    *,
    kinds: Sequence[str] = ("calls", "accesses_field", "imports", "references_doc"),
    limit: int = 100,
    backend: str | None = None,
) -> dict[str, Any]:
    """Inbound edges to `uid` — "who references this?".

    Coverage contract (so silent truncation can't bite the agent):
      - ``count`` is the rows in *this* response (≤ limit).
      - ``total_count`` is the TRUE inbound-edge count across the kinds
        filter. If ``count < total_count`` the response is incomplete —
        the agent must either widen ``limit`` or narrow ``kinds``.
      - ``meta.truncated`` mirrors the same condition for fast inspection.
    """
    try:
        be = _backend(backend=backend)
    except BackendUnavailable as exc:
        return _fail("unavailable", str(exc), retryable=True)
    node, tried_uids = _resolve_uid(be, uid)
    if node is None:
        return _fail_uid_not_found(uid, tried_uids)

    canonical_uid = node.uid
    edges = be.list_edges(target_uid=canonical_uid, edge_types=tuple(kinds), limit=limit)

    # True total — separate count query so the caller knows if `edges`
    # is a complete picture or a slice. Uses the same kinds filter
    # because the backend's list_edges does the same filtering.
    total = _count_edges_for(
        be, target_uid=canonical_uid, edge_types=tuple(kinds)
    )
    truncated = total > len(edges)

    return _ok(
        {
            "node": NodeSummary.from_node(node).to_dict(),
            "references": [_edge_to_dict(e) for e in edges],
            "count": len(edges),
            "total_count": total,
        },
        meta={
            "backend": be.backend_id,
            "kinds": list(kinds),
            "limit": limit,
            "truncated": truncated,
        },
    )


def _count_edges_for(
    backend: GraphBackend,
    *,
    target_uid: str | None = None,
    source_uid: str | None = None,
    edge_types: Sequence[str] | None = None,
) -> int:
    """Count edges matching the filter — separate from list_edges so the
    caller can know "you got N of M". Walks SQLite directly when the
    backend exposes ``_conn`` (the production path); falls back to
    pulling a large list and counting it for stub backends (tests).
    """
    sqlite_conn = getattr(backend, "_conn", None)
    if sqlite_conn is not None:
        where = []
        params: list[Any] = []
        if source_uid is not None:
            where.append("n_src.uid = ?")
            params.append(source_uid)
        if target_uid is not None:
            where.append("n_tgt.uid = ?")
            params.append(target_uid)
        if edge_types:
            placeholders = ",".join("?" * len(edge_types))
            where.append(f"e.edge_type IN ({placeholders})")
            params.extend(edge_types)
        clause = ("WHERE " + " AND ".join(where)) if where else ""
        sql = f"""
          SELECT COUNT(*)
          FROM graph_edges_v12 e
          JOIN graph_nodes n_src ON n_src.id = e.source_id
          JOIN graph_nodes n_tgt ON n_tgt.id = e.target_id
          {clause}
        """
        return int(sqlite_conn.execute(sql, params).fetchone()[0])
    # Stub backend path — pull a generous slice and count it.
    edges = backend.list_edges(
        source_uid=source_uid,
        target_uid=target_uid,
        edge_types=tuple(edge_types) if edge_types else None,
        limit=10_000,
    )
    return len(edges)


def cos_graph_path(
    source_uid: str,
    target_uid: str,
    *,
    max_hops: int = 5,
    backend: str | None = None,
) -> dict[str, Any]:
    """Shortest path between two nodes (any direction).

    B4: each hop pulls up to 1000 edges from the backend (up from 200).
    When either side's edge list hits that cap the result is flagged
    ``meta.truncated=True`` so callers know the search may have missed a
    shorter path that lives beyond the first 1000 neighbours.
    """
    try:
        be = _backend(backend=backend)
    except BackendUnavailable as exc:
        return _fail("unavailable", str(exc), retryable=True)
    src_node, tried_src = _resolve_uid(be, source_uid)
    if src_node is None:
        return _fail_uid_not_found(source_uid, tried_src, label="source_uid")
    tgt_node, tried_tgt = _resolve_uid(be, target_uid)
    if tgt_node is None:
        return _fail_uid_not_found(target_uid, tried_tgt, label="target_uid")
    source_uid = src_node.uid
    target_uid = tgt_node.uid
    _PATH_HOP_LIMIT = 1000
    truncated = False
    parents: dict[str, tuple[str, GraphEdge] | None] = {source_uid: None}
    queue: deque[tuple[str, int]] = deque([(source_uid, 0)])
    while queue:
        uid, depth = queue.popleft()
        if uid == target_uid:
            break
        if depth >= max_hops:
            continue
        out_edges = be.list_edges(source_uid=uid, limit=_PATH_HOP_LIMIT)
        if len(out_edges) >= _PATH_HOP_LIMIT:
            truncated = True
        for edge in out_edges:
            nxt = edge.target_uid
            if nxt not in parents:
                parents[nxt] = (uid, edge)
                queue.append((nxt, depth + 1))
        in_edges = be.list_edges(target_uid=uid, limit=_PATH_HOP_LIMIT)
        if len(in_edges) >= _PATH_HOP_LIMIT:
            truncated = True
        for edge in in_edges:
            nxt = edge.source_uid
            if nxt not in parents:
                parents[nxt] = (uid, edge)
                queue.append((nxt, depth + 1))
    if target_uid not in parents:
        return _ok(
            {"path": None, "edges": [], "truncated": truncated},
            meta={
                "backend": be.backend_id,
                "reason": "unreachable",
                "truncated": truncated,
                "hop_limit": _PATH_HOP_LIMIT,
            },
        )
    chain: list[GraphEdge] = []
    cur = target_uid
    while parents.get(cur) is not None:
        prev, edge = parents[cur]  # type: ignore[misc]
        chain.append(edge)
        cur = prev
    chain.reverse()
    return _ok(
        {
            "path": [source_uid]
            + [e.target_uid if e.source_uid == source_uid else e.source_uid for e in chain],
            "edges": [_edge_to_dict(e) for e in chain],
            "hops": len(chain),
            "truncated": truncated,
        },
        meta={
            "backend": be.backend_id,
            "truncated": truncated,
            "hop_limit": _PATH_HOP_LIMIT,
        },
    )


# TASK-141: edge categories that drive the new view modes.
_SEMANTIC_EDGES: tuple[str, ...] = (
    "calls",
    "imports",
    "inherits_from",
    "implements",
    "extends",
    "dispatches",
    "handles_route",
    "handles_tool",
    "handles_event",
    "constructs",
    "awaits",
    "references",
    "references_doc",
    "is_decorated_by",
)

_CONTAINS_EDGES: tuple[str, ...] = ("contains",)

# Noise nodes that pollute the graph viewer when shown.  They're real
# graph data (extracted by md_links / frontmatter parsers) but they're
# not navigation targets — they belong in the docs RAG, not the canvas.
_DEFAULT_NOISE_KINDS: frozenset[str] = frozenset(
    {
        # Pure metadata that's already shown in the docs RAG / contains tree —
        # surfacing it on the graph canvas just creates visual noise.
        "doc:frontmatter_key",
        "doc_frontmatter",
        "doc:heading",
        "doc_heading",
        # Unresolved external identifiers (typing.*, builtins, dynamic
        # method accesses) — they're stub nodes synthesised to satisfy
        # FK constraints, not navigation targets. Hidden by default; pass
        # `exclude_kinds=""` to show them when you really need to.
        "identifier",
    }
)


# Diversified blend recipe for the auto mode (TASK-141).  Pulling the
# first N edges by confidence happens to over-represent whichever edge
# type the SQL ORDER BY surfaces first (in the live graph: handles_tool
# at 200+ rows).  Allocating per-bucket quotas guarantees every kind of
# semantic relationship lands in the result.
_AUTO_BLEND_BUCKETS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("calls", ("calls", "constructs")),
    ("imports", ("imports", "re_exports")),
    ("inherit", ("inherits_from", "implements", "extends")),
    ("handle", ("handles_route", "handles_tool", "handles_event", "dispatches", "defines_route")),
    ("type", ("has_param_type", "returns_type", "field_of_type", "accesses_field")),
    # Doc cross-references — `links_to` alone carries 1.5K+ edges; the
    # previous blend had no bucket so auto-mode renderings of the doc
    # subgraph showed nothing but contains spine.
    ("doc_link", ("links_to", "cites_heading", "references_doc", "read_next", "references")),
    # Decorators + module-level declarations.
    ("decoration", ("is_decorated_by", "declares")),
    ("contains", ("contains",)),
)


def cos_graph_export(
    *,
    format: str = "json",
    root_uid: str | None = None,
    edge_types: Sequence[str] | None = None,
    max_nodes: int = 500,
    max_hops: int | None = None,
    include_spine: bool = False,
    mode: str = "auto",
    exclude_kinds: Sequence[str] | None = None,
    backend: str | None = None,
) -> dict[str, Any]:
    """Export a subgraph in `json | mermaid | dot`.

    TASK-141: ``mode`` selects the view-mode blend used when no root is
    pinned.  Hub Graph tab consumes this directly:

      - ``auto`` (default): blend of semantic (~60%) + contains (~40%).
        The previous behaviour returned 100% contains because the SQL
        order-by confidence happens to put `contains` (1.0) first —
        that's the fix the hub UI hairball needed.
      - ``containment``: contains-only (folder → file → class → method).
      - ``dependencies``: semantic-only (calls / imports / handles_* /
        inherits_from / implements / dispatches / awaits / ...).
      - ``processes``: returns Louvain community nodes + their members.

    ``exclude_kinds`` filters noise nodes (frontmatter keys, doc
    headings).  Defaults to a built-in set when None — pass an empty
    list to disable.
    """
    try:
        be = _backend(backend=backend)
    except BackendUnavailable as exc:
        return _fail("unavailable", str(exc), retryable=True)
    if format not in {"json", "mermaid", "dot"}:
        return _fail("validation", f"unknown format {format!r}")
    if mode not in {"auto", "containment", "dependencies", "processes"}:
        return _fail(
            "validation",
            f"mode must be one of auto/containment/dependencies/processes (got {mode!r})",
        )

    excluded = _DEFAULT_NOISE_KINDS if exclude_kinds is None else frozenset(exclude_kinds)

    if root_uid is not None:
        # Hub Graph tab "depth=all" sent max_nodes=10000 but the walk
        # stopped at 3 hops, so subfolder contents never appeared
        # (user-reported: "max doesn't show 100%"). Accept the
        # frontend's depth choice and clamp to a safe ceiling.
        effective_hops = 3 if max_hops is None else max(1, min(int(max_hops), 16))
        nodes, edges = _walk_bfs(
            be,
            root_uid=root_uid,
            direction="both",
            max_hops=effective_hops,
            confidence_min=0.0,
            edge_types=edge_types,
            visit_limit=max_nodes,
        )
    elif mode == "processes":
        nodes, edges = _export_processes(be, max_nodes=max_nodes)
    else:
        nodes, edges = _export_blend(
            be,
            mode=mode,
            edge_types=edge_types,
            max_nodes=max_nodes,
        )

    # TASK-141: apply noise filter.  Drop nodes whose kind is in
    # ``excluded`` AND drop any edges that touch them.
    if excluded:
        nodes = [n for n in nodes if (n.kind or "") not in excluded]
        kept_uids = {n.uid for n in nodes}
        edges = [e for e in edges if e.source_uid in kept_uids and e.target_uid in kept_uids]

    # S3: when include_spine is set, extend the subgraph with the
    # CONTAINS-ancestor chain of the root (or the deepest file node
    # present when no root is specified) so the tree-view has a
    # connected Folder→...→leaf backbone.
    if include_spine:
        seed_uid = root_uid
        if seed_uid is None:
            for n in nodes:
                if (n.kind or "").startswith(("file", "code:file", "doc:file")):
                    seed_uid = n.uid
                    break
        if seed_uid:
            ancestors, spine_edges = _contains_ancestors(be, leaf_uid=seed_uid)
            existing_uids = {n.uid for n in nodes}
            for a in ancestors:
                if a.uid not in existing_uids:
                    nodes.append(a)
                    existing_uids.add(a.uid)
            edges = list(edges) + list(spine_edges)

    if format == "json":
        # Server-side degree map so consumers (3D adapter, search,
        # NodeInspector) all see the same hub score without each
        # recomputing client-side.
        degree_map = _degree_map_for(be, [n.uid for n in nodes])
        payload: dict[str, Any] = {
            "format": "json",
            "nodes": [
                NodeSummary.from_node(n, degree=degree_map.get(n.uid)).to_dict() for n in nodes
            ],
            "edges": [_edge_to_dict(e) for e in edges],
        }
    elif format == "mermaid":
        payload = {"format": "mermaid", "diagram": _to_mermaid(nodes, edges)}
    else:  # dot
        payload = {"format": "dot", "diagram": _to_dot(nodes, edges)}
    return _ok(
        payload,
        meta={
            "backend": be.backend_id,
            "node_count": len(nodes),
            "edge_count": len(edges),
            "include_spine": include_spine,
        },
    )


def _export_blend(
    be: GraphBackend,
    *,
    mode: str,
    edge_types: Sequence[str] | None,
    max_nodes: int,
) -> tuple[list[GraphNode], list[GraphEdge]]:
    """Compose the node + edge list for ``auto`` / ``containment`` /
    ``dependencies`` modes (TASK-141).

    The SQL list_edges API orders by ``(confidence DESC, id ASC)`` so
    a flat call with edge_types=None puts every contains edge
    (confidence=1.0) ahead of every semantic edge.  This helper
    explicitly partitions the budget so semantic relationships always
    land in the result.
    """
    if edge_types is not None:
        edges = list(be.list_edges(edge_types=tuple(edge_types), limit=max_nodes))
    elif mode == "containment":
        edges = list(be.list_edges(edge_types=_CONTAINS_EDGES, limit=max_nodes))
    elif mode == "dependencies":
        # Diversified pull across all semantic buckets so the result
        # isn't dominated by a single kind (e.g. handles_tool when MCP
        # registrations are dense).  Skip the contains bucket here.
        per_bucket = max(1, max_nodes // (len(_AUTO_BLEND_BUCKETS) - 1))
        edges = []
        for _, types in _AUTO_BLEND_BUCKETS:
            if types == _CONTAINS_EDGES:
                continue
            edges.extend(be.list_edges(edge_types=types, limit=per_bucket))
        edges = edges[:max_nodes]
    else:  # mode == "auto"
        # Equal-share quota across every bucket, then trim to budget.
        # Guarantees every semantic kind shows up alongside contains.
        per_bucket = max(1, max_nodes // len(_AUTO_BLEND_BUCKETS))
        edges = []
        for _, types in _AUTO_BLEND_BUCKETS:
            edges.extend(be.list_edges(edge_types=types, limit=per_bucket))
        edges = edges[:max_nodes]

    node_uids: set[str] = set()
    for e in edges:
        node_uids.add(e.source_uid)
        node_uids.add(e.target_uid)
    nodes = [n for n in (be.get_node(u) for u in node_uids) if n is not None]

    # Spine connectivity: walk every node up the ancestor chain so the
    # SPA's tree builder sees a connected forest. Without this, budget-
    # driven exports drop intermediate folder→file edges and the
    # orphans surface as fake "extra roots" (user's screenshot bug).
    # Only kicks in when contains is genuinely in scope — `dependencies`
    # mode promises no contains edges, so we leave its result alone.
    contains_in_scope = (
        edge_types is not None and any(t == "contains" for t in edge_types)
    ) or mode in ("auto", "containment")
    if node_uids and contains_in_scope:
        existing_pairs = {(e.source_uid, e.target_uid, e.edge_type) for e in edges}
        nodes_by_uid = {n.uid: n for n in nodes}
        for uid in list(node_uids):
            ancestors, spine_edges = _contains_ancestors(be, leaf_uid=uid)
            for a in ancestors:
                if a.uid not in nodes_by_uid:
                    nodes_by_uid[a.uid] = a
                    node_uids.add(a.uid)
            for se in spine_edges:
                key = (se.source_uid, se.target_uid, se.edge_type)
                if key not in existing_pairs:
                    edges.append(se)
                    existing_pairs.add(key)
        nodes = list(nodes_by_uid.values())

    return nodes, edges


def _export_processes(
    be: GraphBackend,
    *,
    max_nodes: int,
) -> tuple[list[GraphNode], list[GraphEdge]]:
    """Return the community-driven view (TASK-141 + TASK-075).

    Each Community produces:
      - one synthetic ``cos:community`` node (label = process name)
      - real member nodes (functions / methods / classes)
      - synthetic ``member_of_community`` edges from member → community

    The synthetic nodes / edges are never persisted — they live only
    in the export response so the SPA's `Processes` view has something
    to render without polluting the SQLite tables.
    """
    from .. import communities as comm_mod

    communities, _membership = comm_mod.compute_communities(be, min_size=2)
    if not communities:
        return [], []

    community_nodes: list[GraphNode] = []
    member_nodes_by_uid: dict[str, GraphNode] = {}
    edges: list[GraphEdge] = []
    budget = max_nodes
    for c in communities:
        if budget <= 0:
            break
        community_uid = c.community_id
        community_nodes.append(
            GraphNode(
                uid=community_uid,
                kind="community",
                label=c.name,
                file_path=None,
                metadata={
                    "summary": c.summary,
                    "priority": c.priority,
                    "member_count": c.member_count,
                    "synthetic": True,
                },
            )
        )
        budget -= 1
        for m in c.members:
            if budget <= 0:
                break
            real = be.get_node(m["uid"])
            if real is None:
                continue
            if real.uid not in member_nodes_by_uid:
                member_nodes_by_uid[real.uid] = real
                budget -= 1
            edges.append(
                GraphEdge(
                    source_uid=real.uid,
                    target_uid=community_uid,
                    edge_type="member_of_community",
                    extractor="communities@v1",
                    confidence=1.0,
                )
            )
    return community_nodes + list(member_nodes_by_uid.values()), edges


def cos_graph_rename_plan(
    uid: str,
    new_name: str,
    *,
    check_strings: bool = True,
    backend: str | None = None,
) -> dict[str, Any]:
    """Produce a rename plan — call-sites, docs, tests, strings."""
    if not new_name or not new_name.strip():
        return _fail("validation", "new_name must be non-empty")
    try:
        be = _backend(backend=backend)
    except BackendUnavailable as exc:
        return _fail("unavailable", str(exc), retryable=True)
    root, tried_uids = _resolve_uid(be, uid)
    if root is None:
        return _fail_uid_not_found(uid, tried_uids)
    uid = root.uid

    call_sites = [
        _edge_to_dict(e)
        for e in be.list_edges(
            target_uid=uid, edge_types=("calls", "accesses_field", "imports"), limit=500
        )
    ]
    doc_refs = [
        _edge_to_dict(e)
        for e in be.list_edges(
            target_uid=uid, edge_types=("links_to", "cites_heading", "references_doc"), limit=500
        )
    ]
    test_refs = [
        _edge_to_dict(e)
        for e in be.list_edges(target_uid=uid, edge_types=("tested_by",), limit=500)
    ]
    risk = "high" if len(call_sites) > 20 else "medium" if call_sites else "low"

    return _ok(
        {
            "old_name": root.label,
            "new_name": new_name,
            "uid": root.uid,
            "call_sites": call_sites,
            "doc_references": doc_refs,
            "test_references": test_refs,
            "string_literals": [] if not check_strings else _grep_string_literals(root.label or ""),
            "risk": risk,
            "suggested_order": [
                "tests first",
                "implementation",
                "docs",
                "string literals last",
            ],
            "confidence": 0.9 if call_sites else 0.6,
        },
        meta={"backend": be.backend_id},
    )


def cos_graph_contracts(
    *,
    scope: str = "all",
    kinds: Sequence[str] = ("http", "mcp", "grpc", "event", "websocket"),
    backend: str | None = None,
) -> dict[str, Any]:
    """API surface — enumerate every route / tool / event handler."""
    try:
        be = _backend(backend=backend)
    except BackendUnavailable as exc:
        return _fail("unavailable", str(exc), retryable=True)

    buckets: dict[str, list[dict[str, Any]]] = {
        "http_routes": [],
        "mcp_tools": [],
        "grpc_endpoints": [],
        "event_handlers": [],
        "websocket": [],
    }
    for edge_type in ("handles_route", "handles_tool", "handles_event"):
        for edge in be.list_edges(edge_types=(edge_type,), limit=2000):
            node = be.get_node(edge.target_uid)
            if node is None:
                continue
            kind = (node.metadata or {}).get("kind", "http")
            if kind not in kinds:
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
    return _ok(
        {"scope": scope, **buckets, "count": sum(len(v) for v in buckets.values())},
        meta={"backend": be.backend_id, "kinds": list(kinds)},
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_node_content(node: GraphNode, *, cap: int = 2000) -> dict[str, Any] | None:
    """B21: read source snippet for a node from its file_path + line range."""
    if not node.file_path:
        return None
    try:
        src = Path(node.file_path)
        if not src.is_file():
            return None
        lines = src.read_text(encoding="utf-8", errors="replace").splitlines()
        start = max(0, (node.start_line or 1) - 1)  # 1-indexed → 0-indexed
        end = node.end_line or node.start_line or len(lines)
        snippet = "\n".join(lines[start:end])
        truncated = len(snippet) > cap
        return {"content": snippet[:cap], "truncated": truncated}
    except Exception as exc:
        logger.debug("_read_node_content skipped for %s: %s", node.uid, exc)
        return None


def _fuzzy_resolve(backend: GraphBackend, needle: str) -> GraphNode | None:
    """Fallback for `cos_graph_context("UserService")` — try a label match.

    Scans edges to collect nodes, then difflib-scores by label. Bounded
    to 200 candidates so latency is predictable.
    """
    lower = needle.lower()
    seen: dict[str, GraphNode] = {}
    for edge in backend.list_edges(limit=500):
        for side in (edge.source_uid, edge.target_uid):
            if side in seen:
                continue
            node = backend.get_node(side)
            if node is None:
                continue
            if needle in (node.uid or "") or lower in (node.label or "").lower():
                return node
            seen[side] = node
    return None


def _lexical_search(
    backend: GraphBackend,
    *,
    q: str,
    kinds: Sequence[str] | None,
    limit: int,
    max_hops: int,
) -> list[GraphNode]:
    """Multi-signal lexical search with centrality tie-breaker."""
    lower = q.lower()
    sqlite_conn = getattr(backend, "_conn", None)
    candidates: list[GraphNode] = []
    if sqlite_conn is not None:
        rows: list[Any] = []
        try:
            if not lower and kinds:
                # kinds-only browse — no text filter needed
                placeholders = ",".join(["?"] * len(kinds))
                rows = sqlite_conn.execute(
                    f"SELECT kind, label, uid, file_path, start_line, end_line,"
                    f"       signature, lang, doc_blob, ast_hash, content_hash,"
                    f"       metadata_json"
                    f" FROM graph_nodes WHERE kind IN ({placeholders}) LIMIT ?",
                    tuple(list(kinds) + [int(limit) * 6]),
                ).fetchall()
            else:
                like_q = f"%{lower}%"
                kinds_clause = ""
                params: list[Any] = [like_q, like_q, like_q]
                if kinds:
                    placeholders = ",".join(["?"] * len(kinds))
                    kinds_clause = f" AND kind IN ({placeholders})"
                    params.extend(list(kinds))
                params.append(int(limit) * 6)
                rows = sqlite_conn.execute(
                    f"""
                    SELECT kind, label, uid, file_path, start_line, end_line,
                           signature, lang, doc_blob, ast_hash, content_hash,
                           metadata_json
                    FROM graph_nodes
                    WHERE (LOWER(label) LIKE ?
                           OR LOWER(COALESCE(signature, '')) LIKE ?
                           OR LOWER(COALESCE(doc_blob, '')) LIKE ?)
                    {kinds_clause}
                    LIMIT ?
                    """,
                    tuple(params),
                ).fetchall()
        except Exception as exc:
            logger.debug("lexical sql search suppressed: %s", exc)
        row_to_node = getattr(backend, "_row_to_node", None)
        for row in rows:
            if row_to_node is not None:
                candidates.append(row_to_node(row))
            else:
                n = backend.get_node(row[2])
                if n is not None:
                    candidates.append(n)

    if not candidates:
        seen: dict[str, GraphNode] = {}
        for edge in backend.list_edges(limit=1000):
            for side in (edge.source_uid, edge.target_uid):
                if side in seen:
                    continue
                node = backend.get_node(side)
                if node is None:
                    continue
                if kinds and node.kind not in kinds:
                    continue
                haystack = " ".join(
                    filter(
                        None,
                        [node.uid, node.label, node.signature, node.doc_blob],
                    )
                ).lower()
                if lower in haystack:
                    seen[side] = node
                if len(seen) >= limit * 3:
                    break
        candidates = list(seen.values())

    degree_map = _degree_map_for(backend, [n.uid for n in candidates])
    from math import log2

    def score(n: GraphNode) -> float:
        label = (n.label or "").lower()
        sig = (n.signature or "").lower()
        doc = (n.doc_blob or "").lower()
        if label == lower:
            base = 1.0
        elif label.startswith(lower):
            base = 0.85
        elif lower in label:
            base = 0.70
        elif lower in sig:
            base = 0.45
        elif lower in doc:
            base = 0.30
        else:
            base = difflib.SequenceMatcher(None, lower, label).ratio() * 0.5
        boost = log2((degree_map.get(n.uid) or 0) + 1) * 0.05
        return base + min(boost, 0.4)

    return sorted(candidates, key=score, reverse=True)[:limit]


def _grep_string_literals(name: str) -> list[dict[str, Any]]:
    """Stub for the string-scan path. Real implementation lives in CLI layer."""
    return []


def _to_mermaid(nodes: Iterable[GraphNode], edges: Iterable[GraphEdge]) -> str:
    lines = ["graph LR"]
    for n in nodes:
        lines.append(f'  {_safe_id(n.uid)}["{_escape(n.label or n.uid)}"]')
    for e in edges:
        lines.append(f"  {_safe_id(e.source_uid)} -->|{e.edge_type}| {_safe_id(e.target_uid)}")
    return "\n".join(lines)


def _to_dot(nodes: Iterable[GraphNode], edges: Iterable[GraphEdge]) -> str:
    lines = ["digraph G {"]
    for n in nodes:
        lines.append(f'  "{_safe_id(n.uid)}" [label="{_escape(n.label or n.uid)}"]')
    for e in edges:
        lines.append(
            f'  "{_safe_id(e.source_uid)}" -> "{_safe_id(e.target_uid)}" [label="{e.edge_type}"]'
        )
    lines.append("}")
    return "\n".join(lines)


def _safe_id(uid: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", uid)[:60]


def _escape(text: str) -> str:
    return text.replace('"', "'")


def cos_graph_entrypoints(
    *,
    top: int = 20,
    kind: str | None = None,
    min_score: float = 0.05,
    backend: str | None = None,
) -> dict[str, Any]:
    """Return scored entry-point candidates (TASK-081)."""
    if not isinstance(top, int) or top <= 0:
        return _fail("validation", "top must be a positive int")
    if top > 200:
        top = 200
    if kind is not None and kind not in ("main", "cli", "http", "cron", "test"):
        return _fail(
            "validation",
            f"kind must be one of main/cli/http/cron/test (got {kind!r})",
        )
    try:
        be = _backend(backend=backend)
    except BackendUnavailable as exc:
        return _fail("unavailable", str(exc), retryable=True)

    try:
        from .. import entry_points as ep_mod  # type: ignore[attr-defined]
    except ImportError as exc:
        return _fail(
            "unavailable",
            f"entry_points module not installed: {exc}",
            retryable=False,
        )

    eps = ep_mod.discover(be, min_score=float(min_score), kind_filter=kind)
    rows = [ep.to_dict() for ep in eps[:top]]
    return _ok(
        {"entrypoints": rows},
        meta={
            "backend": be.backend_id,
            "count": len(rows),
            "scanned_kinds": list(("code:function", "code:method", "function", "method")),
        },
    )


def cos_graph_communities(
    *,
    top: int = 50,
    min_size: int = 2,
    backend: str | None = None,
) -> dict[str, Any]:
    """Return Louvain-detected processes / communities (TASK-075)."""
    if not isinstance(top, int) or top <= 0:
        return _fail("validation", "top must be a positive int")
    if top > 200:
        top = 200
    if not isinstance(min_size, int) or min_size < 1:
        return _fail("validation", "min_size must be >= 1")
    try:
        be = _backend(backend=backend)
    except BackendUnavailable as exc:
        return _fail("unavailable", str(exc), retryable=True)

    from .. import communities as comm_mod

    all_communities, _membership = comm_mod.compute_communities(be, min_size=int(min_size))
    rows = comm_mod.communities_to_processes(all_communities, relevant_uids=None)
    return _ok(
        {"processes": rows[:top]},
        meta={
            "backend": be.backend_id,
            "count": len(rows[:top]),
            "total": len(rows),
        },
    )


def cos_graph_centrality(
    *,
    top: int = 20,
    kind: str | None = None,
    metric: str = "degree",
    backend: str | None = None,
) -> dict[str, Any]:
    """Hub detection via degree (or betweenness) centrality."""
    if not isinstance(top, int) or top <= 0:
        return _fail("validation", "top must be a positive int")
    if top > 200:
        top = 200
    if metric not in ("degree", "betweenness"):
        return _fail("validation", "metric must be 'degree' or 'betweenness'")
    try:
        be = _backend(backend=backend)
    except BackendUnavailable as exc:
        return _fail("unavailable", str(exc), retryable=True)

    sqlite_conn = getattr(be, "_conn", None)
    truncated = False

    if sqlite_conn is not None:
        try:
            kind_clause = ""
            params: list[Any] = []
            if kind:
                kind_clause = "WHERE n.kind = ?"
                params.append(kind)

            in_deg_rows = sqlite_conn.execute(
                f"""
                SELECT n.uid, n.kind, n.label, COUNT(e.id) AS cnt
                FROM graph_nodes n
                LEFT JOIN graph_edges_v12 e ON e.target_id = n.id
                {kind_clause}
                GROUP BY n.id
                """,
                tuple(params),
            ).fetchall()
            out_deg_rows = sqlite_conn.execute(
                f"""
                SELECT n.uid, COUNT(e.id) AS cnt
                FROM graph_nodes n
                LEFT JOIN graph_edges_v12 e ON e.source_id = n.id
                {kind_clause}
                GROUP BY n.id
                """,
                tuple(params),
            ).fetchall()
        except Exception as exc:
            logger.debug("centrality SQL suppressed: %s", exc)
            in_deg_rows = []
            out_deg_rows = []

        out_map = {row[0]: int(row[1]) for row in out_deg_rows}
        N = len(in_deg_rows)
        norm = 2 * (N - 1) if N > 1 else 1
        rows_out = []
        for uid, nkind, label, in_cnt in in_deg_rows:
            out_cnt = out_map.get(uid, 0)
            in_cnt = int(in_cnt)
            score = (in_cnt + out_cnt) / norm
            rows_out.append(
                {
                    "uid": uid,
                    "kind": nkind,
                    "label": label,
                    "in_degree": in_cnt,
                    "out_degree": out_cnt,
                    "centrality_score": round(score, 6),
                }
            )
    else:
        # Fallback: scan edges
        in_deg: dict[str, int] = {}
        out_deg: dict[str, int] = {}
        uid_meta: dict[str, tuple[str, str]] = {}  # uid -> (kind, label)
        for edge in be.list_edges(limit=10000):
            out_deg[edge.source_uid] = out_deg.get(edge.source_uid, 0) + 1
            in_deg[edge.target_uid] = in_deg.get(edge.target_uid, 0) + 1
        all_uids = set(in_deg) | set(out_deg)
        if kind:
            filtered_uids = set()
            for u in all_uids:
                node = be.get_node(u)
                if node and node.kind == kind:
                    filtered_uids.add(u)
                    uid_meta[u] = (node.kind or "", node.label or "")
            all_uids = filtered_uids
        else:
            for u in all_uids:
                node = be.get_node(u)
                if node:
                    uid_meta[u] = (node.kind or "", node.label or "")
        N = len(all_uids)
        norm = 2 * (N - 1) if N > 1 else 1
        rows_out = []
        for u in all_uids:
            ic = in_deg.get(u, 0)
            oc = out_deg.get(u, 0)
            meta_entry = uid_meta.get(u, ("", u))
            rows_out.append(
                {
                    "uid": u,
                    "kind": meta_entry[0],
                    "label": meta_entry[1],
                    "in_degree": ic,
                    "out_degree": oc,
                    "centrality_score": round((ic + oc) / norm, 6),
                }
            )

    if metric == "betweenness" and sqlite_conn is not None:
        _BETWEENNESS_CAP = 300
        try:
            all_uids_list: list[str] = [r["uid"] for r in rows_out]
            if len(all_uids_list) > _BETWEENNESS_CAP:
                # Approximate: sample the top-degree nodes only.
                rows_out.sort(key=lambda r: r["centrality_score"], reverse=True)
                all_uids_list = [r["uid"] for r in rows_out[:_BETWEENNESS_CAP]]
                truncated = True
            uid_idx = {u: i for i, u in enumerate(all_uids_list)}
            adj: dict[int, list[int]] = {i: [] for i in range(len(all_uids_list))}
            for u in all_uids_list:
                i = uid_idx[u]
                edges_out = be.list_edges(source_uid=u, limit=500)
                for e in edges_out:
                    j = uid_idx.get(e.target_uid)
                    if j is not None:
                        adj[i].append(j)
            betweenness = _betweenness_centrality(adj, len(all_uids_list))
            bt_map = {all_uids_list[i]: v for i, v in enumerate(betweenness)}
            for r in rows_out:
                r["centrality_score"] = round(bt_map.get(r["uid"], 0.0), 6)
        except Exception as exc:
            logger.debug("betweenness computation suppressed: %s", exc)

    rows_out.sort(key=lambda r: r["centrality_score"], reverse=True)
    return _ok(
        {"nodes": rows_out[:top]},
        meta={
            "backend": be.backend_id,
            "metric": metric,
            "node_count": len(rows_out),
            "truncated": truncated,
        },
    )


def _betweenness_centrality(adj: dict[int, list[int]], n: int) -> list[float]:
    """Brandes' algorithm — O(V·E) exact betweenness for small graphs."""
    bet = [0.0] * n
    for s in range(n):
        stack: list[int] = []
        pred: list[list[int]] = [[] for _ in range(n)]
        sigma = [0] * n
        sigma[s] = 1
        dist = [-1] * n
        dist[s] = 0
        from collections import deque as _deque

        q: _deque[int] = _deque([s])
        while q:
            v = q.popleft()
            stack.append(v)
            for w in adj.get(v, []):
                if dist[w] < 0:
                    dist[w] = dist[v] + 1
                    q.append(w)
                if dist[w] == dist[v] + 1:
                    sigma[w] += sigma[v]
                    pred[w].append(v)
        delta = [0.0] * n
        while stack:
            w = stack.pop()
            for v in pred[w]:
                if sigma[w]:
                    delta[v] += (sigma[v] / sigma[w]) * (1 + delta[w])
            if w != s:
                bet[w] += delta[w]
    norm_factor = (n - 1) * (n - 2) if n > 2 else 1
    return [v / norm_factor for v in bet]


def cos_graph_ranking(
    *,
    query: str | None = None,
    top: int = 20,
    kind: str | None = None,
    damping: float = 0.85,
    iterations: int = 30,
    backend: str | None = None,
) -> dict[str, Any]:
    """PageRank-based node ranking with optional query personalisation."""
    if not isinstance(top, int) or top <= 0:
        return _fail("validation", "top must be a positive int")
    if top > 200:
        top = 200
    if not (0.0 < damping < 1.0):
        return _fail("validation", "damping must be in (0, 1)")
    try:
        be = _backend(backend=backend)
    except BackendUnavailable as exc:
        return _fail("unavailable", str(exc), retryable=True)

    _NODE_CAP = 5000
    truncated = False
    sqlite_conn = getattr(be, "_conn", None)

    if sqlite_conn is not None:
        try:
            kind_filter = "WHERE kind = ?" if kind else ""
            params_n: list[Any] = ([kind] if kind else []) + [_NODE_CAP]
            uid_rows = sqlite_conn.execute(
                f"SELECT id, uid, kind, label, file_path, start_line "
                f"FROM graph_nodes {kind_filter} LIMIT ?",
                tuple(params_n),
            ).fetchall()
            if len(uid_rows) >= _NODE_CAP:
                truncated = True
            edge_rows = sqlite_conn.execute(
                "SELECT source_id, target_id FROM graph_edges_v12 LIMIT ?",
                (_NODE_CAP * 20,),
            ).fetchall()
        except Exception as exc:
            logger.debug("ranking SQL suppressed: %s", exc)
            uid_rows = []
            edge_rows = []
        int_to_uid = {row[0]: row[1] for row in uid_rows}
        int_to_meta: dict[int, tuple[str, str, str | None, int | None]] = {
            row[0]: (row[2], row[3], row[4], row[5]) for row in uid_rows
        }
        uid_to_int: dict[str, int] = {row[1]: row[0] for row in uid_rows}
        valid_ids = set(int_to_uid)
        out_links: dict[int, list[int]] = {i: [] for i in valid_ids}
        for src, tgt in edge_rows:
            if src in valid_ids and tgt in valid_ids:
                out_links[src].append(tgt)
        N = len(valid_ids)
        node_ids = list(valid_ids)
    else:
        # Edge-scan fallback
        uid_set: set[str] = set()
        edge_pairs: list[tuple[str, str]] = []
        for edge in be.list_edges(limit=_NODE_CAP * 10):
            uid_set.add(edge.source_uid)
            uid_set.add(edge.target_uid)
            edge_pairs.append((edge.source_uid, edge.target_uid))
        if len(uid_set) > _NODE_CAP:
            truncated = True
        node_ids_str = list(uid_set)[:_NODE_CAP]
        uid_to_int = {u: i for i, u in enumerate(node_ids_str)}
        int_to_uid = {i: u for i, u in enumerate(node_ids_str)}
        int_to_meta = {}
        valid_ids_int = set(range(len(node_ids_str)))
        out_links_str: dict[int, list[int]] = {i: [] for i in valid_ids_int}
        for s, t in edge_pairs:
            si, ti = uid_to_int.get(s, -1), uid_to_int.get(t, -1)
            if si >= 0 and ti >= 0:
                out_links_str[si].append(ti)
        out_links = out_links_str
        N = len(node_ids_str)
        node_ids = list(valid_ids_int)
        # Kind filter post-hoc
        if kind:
            keep = set()
            for nid in node_ids:
                u = int_to_uid.get(nid, "")
                node = be.get_node(u)
                if node and node.kind == kind:
                    keep.add(nid)
                    int_to_meta[nid] = (
                        node.kind or "",
                        node.label or "",
                        node.file_path,
                        node.start_line,
                    )
            node_ids = [n for n in node_ids if n in keep]
            N = len(node_ids)

    if N == 0:
        return _ok({"nodes": []}, meta={"backend": be.backend_id, "count": 0})

    # Personalisation vector: uniform unless query given.
    personalized: dict[int, float] = {}
    if query:
        lower_q = query.lower()
        for nid in node_ids:
            meta_entry = int_to_meta.get(nid)
            label = meta_entry[1] if meta_entry else (int_to_uid.get(nid, ""))
            if lower_q in label.lower():
                personalized[nid] = 1.0
        total_p = sum(personalized.values())
        if total_p:
            personalized = {k: v / total_p for k, v in personalized.items()}

    # Power iteration
    rank: dict[int, float] = dict.fromkeys(node_ids, 1.0 / N)
    dangling = {nid for nid in node_ids if not out_links.get(nid)}
    for _ in range(iterations):
        dangling_sum = sum(rank[nid] for nid in dangling) / N
        new_rank: dict[int, float] = {}
        for nid in node_ids:
            inbound = [src for src in node_ids if nid in out_links.get(src, [])]
            push = sum(rank[src] / len(out_links[src]) for src in inbound if out_links.get(src))
            if personalized:
                teleport = personalized.get(nid, 0.0)
            else:
                teleport = 1.0 / N
            new_rank[nid] = (1 - damping) * teleport + damping * (push + dangling_sum)
        rank = new_rank

    results: list[dict[str, Any]] = []
    for nid, score in sorted(rank.items(), key=lambda x: x[1], reverse=True)[:top]:
        uid = int_to_uid.get(nid, "")
        meta_entry = int_to_meta.get(nid)
        if meta_entry:
            nkind, label, fpath, sline = meta_entry
        else:
            node = be.get_node(uid)
            nkind = node.kind or "" if node else ""
            label = node.label or uid if node else uid
            fpath = node.file_path if node else None
            sline = node.start_line if node else None
        results.append(
            {
                "uid": uid,
                "kind": nkind,
                "label": label,
                "rank_score": round(score, 8),
                "file_path": fpath,
                "start_line": sline,
            }
        )

    return _ok(
        {"nodes": results},
        meta={
            "backend": be.backend_id,
            "node_count": N,
            "iterations": iterations,
            "damping": damping,
            "truncated": truncated,
            "personalized": bool(personalized),
        },
    )


def cos_graph_doctor(
    *,
    fix: bool = False,
    backend: str | None = None,
) -> dict[str, Any]:
    """Graph health check — orphans, dangling edges, duplicates."""
    try:
        be = _backend(backend=backend)
    except BackendUnavailable as exc:
        return _fail("unavailable", str(exc), retryable=True)

    sqlite_conn = getattr(be, "_conn", None)
    issues: list[dict[str, Any]] = []
    stats: dict[str, Any] = {}
    fixed_count = 0

    if sqlite_conn is not None:
        try:
            node_count = sqlite_conn.execute("SELECT COUNT(*) FROM graph_nodes").fetchone()[0]
            edge_count = sqlite_conn.execute("SELECT COUNT(*) FROM graph_edges_v12").fetchone()[0]
            stats["node_count"] = node_count
            stats["edge_count"] = edge_count

            # 1. Dangling source edges (source_id FK points to deleted node)
            dangling_src_rows = sqlite_conn.execute(
                """
                SELECT e.id, ns.uid, nt.uid
                FROM graph_edges_v12 e
                LEFT JOIN graph_nodes ns ON ns.id = e.source_id
                LEFT JOIN graph_nodes nt ON nt.id = e.target_id
                WHERE ns.id IS NULL
                LIMIT 100
                """
            ).fetchall()
            dangling_src_count = sqlite_conn.execute(
                """
                SELECT COUNT(*) FROM graph_edges_v12 e
                LEFT JOIN graph_nodes ns ON ns.id = e.source_id
                WHERE ns.id IS NULL
                """
            ).fetchone()[0]
            if dangling_src_count:
                issues.append(
                    {
                        "category": "dangling_source",
                        "count": dangling_src_count,
                        "sample": [
                            {"edge_id": r[0], "source_uid": r[1], "target_uid": r[2]}
                            for r in dangling_src_rows[:5]
                        ],
                    }
                )
                if fix:
                    ids_to_del = [r[0] for r in dangling_src_rows]
                    if ids_to_del:
                        placeholders = ",".join("?" * len(ids_to_del))
                        sqlite_conn.execute(
                            f"DELETE FROM graph_edges_v12 WHERE id IN ({placeholders})",
                            ids_to_del,
                        )
                        sqlite_conn.commit()
                        fixed_count += len(ids_to_del)

            # 2. Dangling target edges (target_id FK points to deleted node)
            dangling_tgt_count = sqlite_conn.execute(
                """
                SELECT COUNT(*) FROM graph_edges_v12 e
                LEFT JOIN graph_nodes nt ON nt.id = e.target_id
                WHERE nt.id IS NULL
                """
            ).fetchone()[0]
            if dangling_tgt_count:
                dangling_tgt_rows = sqlite_conn.execute(
                    """
                    SELECT e.id, ns.uid, nt.uid
                    FROM graph_edges_v12 e
                    LEFT JOIN graph_nodes ns ON ns.id = e.source_id
                    LEFT JOIN graph_nodes nt ON nt.id = e.target_id
                    WHERE nt.id IS NULL
                    LIMIT 5
                    """
                ).fetchall()
                issues.append(
                    {
                        "category": "dangling_target",
                        "count": dangling_tgt_count,
                        "sample": [
                            {"edge_id": r[0], "source_uid": r[1], "target_uid": r[2]}
                            for r in dangling_tgt_rows
                        ],
                    }
                )
                if fix:
                    all_dangling_tgt = sqlite_conn.execute(
                        """
                        SELECT e.id FROM graph_edges_v12 e
                        LEFT JOIN graph_nodes nt ON nt.id = e.target_id
                        WHERE nt.id IS NULL
                        """
                    ).fetchall()
                    ids_to_del = [r[0] for r in all_dangling_tgt]
                    if ids_to_del:
                        placeholders = ",".join("?" * len(ids_to_del))
                        sqlite_conn.execute(
                            f"DELETE FROM graph_edges_v12 WHERE id IN ({placeholders})",
                            ids_to_del,
                        )
                        sqlite_conn.commit()
                        fixed_count += len(ids_to_del)

            # 3. Duplicate edges (same source_id/target_id/edge_type/extractor)
            dup_count = sqlite_conn.execute(
                """
                SELECT COUNT(*) FROM (
                  SELECT source_id, target_id, edge_type, extractor,
                         COUNT(*) AS cnt
                  FROM graph_edges_v12
                  GROUP BY source_id, target_id, edge_type, extractor
                  HAVING cnt > 1
                )
                """
            ).fetchone()[0]
            if dup_count:
                dup_sample = sqlite_conn.execute(
                    """
                    SELECT ns.uid, nt.uid, e.edge_type, e.extractor,
                           COUNT(*) AS cnt
                    FROM graph_edges_v12 e
                    LEFT JOIN graph_nodes ns ON ns.id = e.source_id
                    LEFT JOIN graph_nodes nt ON nt.id = e.target_id
                    GROUP BY e.source_id, e.target_id, e.edge_type, e.extractor
                    HAVING cnt > 1
                    ORDER BY cnt DESC
                    LIMIT 5
                    """
                ).fetchall()
                issues.append(
                    {
                        "category": "duplicate_edges",
                        "count": dup_count,
                        "sample": [
                            {
                                "source_uid": r[0],
                                "target_uid": r[1],
                                "edge_type": r[2],
                                "extractor": r[3],
                                "count": r[4],
                            }
                            for r in dup_sample
                        ],
                    }
                )

            # 4. Orphaned nodes (nodes with zero edges in either direction)
            orphan_count = sqlite_conn.execute(
                """
                SELECT COUNT(*) FROM graph_nodes n
                LEFT JOIN graph_edges_v12 src ON src.source_id = n.id
                LEFT JOIN graph_edges_v12 tgt ON tgt.target_id = n.id
                WHERE src.id IS NULL AND tgt.id IS NULL
                """
            ).fetchone()[0]
            stats["orphaned_nodes"] = orphan_count
            if orphan_count > 0:
                orphan_sample = sqlite_conn.execute(
                    """
                    SELECT n.uid, n.kind, n.label
                    FROM graph_nodes n
                    LEFT JOIN graph_edges_v12 src ON src.source_id = n.id
                    LEFT JOIN graph_edges_v12 tgt ON tgt.target_id = n.id
                    WHERE src.id IS NULL AND tgt.id IS NULL
                    LIMIT 5
                    """
                ).fetchall()
                issues.append(
                    {
                        "category": "orphaned_nodes",
                        "count": orphan_count,
                        "sample": [
                            {"uid": r[0], "kind": r[1], "label": r[2]} for r in orphan_sample
                        ],
                    }
                )

            # 5. Self-loop edges (source_id == target_id — extractor bugs)
            self_loop_count = sqlite_conn.execute(
                "SELECT COUNT(*) FROM graph_edges_v12 WHERE source_id = target_id"
            ).fetchone()[0]
            if self_loop_count:
                sl_sample = sqlite_conn.execute(
                    """
                    SELECT ns.uid, e.edge_type FROM graph_edges_v12 e
                    LEFT JOIN graph_nodes ns ON ns.id = e.source_id
                    WHERE e.source_id = e.target_id LIMIT 5
                    """
                ).fetchall()
                issues.append(
                    {
                        "category": "self_loops",
                        "count": self_loop_count,
                        "sample": [{"uid": r[0], "edge_type": r[1]} for r in sl_sample],
                    }
                )

            # 6. Stale-path nodes — file_path points to a file that no
            # longer exists on disk. Accumulates when files move (e.g.
            # the `core/` → `src/core/` reorg left 3.7K ghost nodes
            # invisible to the dangling/orphan/self_loop checks because
            # ghosts had their own internal contains-children tree).
            distinct_paths = [
                r[0]
                for r in sqlite_conn.execute(
                    "SELECT DISTINCT file_path FROM graph_nodes "
                    "WHERE file_path IS NOT NULL AND file_path != ''"
                ).fetchall()
            ]
            repo_root = _repo_root_for_paths()
            stale_paths = [
                p for p in distinct_paths if not (repo_root / p).exists()
            ]
            if stale_paths:
                stale_node_count = sqlite_conn.execute(
                    f"SELECT COUNT(*) FROM graph_nodes WHERE file_path IN ({','.join('?' * len(stale_paths))})",
                    stale_paths,
                ).fetchone()[0]
                sp_sample = sqlite_conn.execute(
                    f"SELECT uid, kind, file_path FROM graph_nodes WHERE file_path IN ({','.join('?' * len(stale_paths))}) LIMIT 5",
                    stale_paths,
                ).fetchall()
                issues.append(
                    {
                        "category": "stale_paths",
                        "count": stale_node_count,
                        "path_count": len(stale_paths),
                        "sample": [
                            {"uid": r[0], "kind": r[1], "file_path": r[2]} for r in sp_sample
                        ],
                    }
                )
                if fix:
                    chunk = 500
                    for i in range(0, len(stale_paths), chunk):
                        batch = stale_paths[i : i + chunk]
                        cur = sqlite_conn.execute(
                            f"DELETE FROM graph_nodes WHERE file_path IN ({','.join('?' * len(batch))})",
                            batch,
                        )
                        fixed_count += int(cur.rowcount or 0)
                    sqlite_conn.commit()

            stats["issue_count"] = len(issues)
            if fix:
                stats["fixed_edge_count"] = fixed_count

        except Exception as exc:
            logger.debug("doctor SQL suppressed: %s", exc)
            return _ok(
                {"healthy": None, "issues": [], "stats": {}, "error": str(exc)},
                meta={"backend": be.backend_id},
            )
    else:
        # Non-SQLite backend: basic edge-endpoint check only
        seen_uids: set[str] = set()
        edge_list = be.list_edges(limit=5000)
        for edge in edge_list:
            seen_uids.add(edge.source_uid)
            seen_uids.add(edge.target_uid)
        missing = 0
        for u in list(seen_uids)[:500]:
            if be.get_node(u) is None:
                missing += 1
        if missing:
            issues.append({"category": "dangling_endpoints", "count": missing, "sample": []})
        stats["edge_count"] = len(edge_list)
        stats["issue_count"] = len(issues)

    healthy = len(issues) == 0
    return _ok(
        {"healthy": healthy, "issues": issues, "stats": stats},
        meta={
            "backend": be.backend_id,
            "fix_applied": fix and fixed_count > 0,
            "fixed_count": fixed_count,
        },
    )


def cos_graph_resolve(
    q: str,
    *,
    kinds: Sequence[str] | None = None,
    top: int = 10,
    backend: str | None = None,
) -> dict[str, Any]:
    """Resolve a natural-language label, path, or partial uid to canonical uids.

    Tries three strategies in order, stopping at the first that yields hits:

    1. Direct uid lookup (when `q` already carries `code:`/`doc:`/`folder:`).
    2. Path-shaped fallback (paths, `::`-separated qualnames) → ``_resolve_uid``.
    3. FTS5 full-text search over label + signature + doc_blob — handles
       multi-word natural-language queries like "the dispatcher function"
       far better than the LIKE pattern used by ``cos_graph_query``.
    """
    if not q or not q.strip():
        return _fail("validation", "q must be a non-empty string")
    try:
        be = _backend(backend=backend)
    except BackendUnavailable as exc:
        return _fail("unavailable", str(exc), retryable=True)

    candidate = q.strip()
    kinds_set = set(kinds) if kinds else None
    candidates: list[GraphNode] = []
    strategy = ""

    # Strategy 1 + 2: direct uid / path-shape resolve.
    looks_pathlike = (
        "/" in candidate
        or "::" in candidate
        or candidate.endswith((".py", ".ts", ".tsx", ".sh", ".md", ".yaml"))
        or _looks_prefixed(candidate)
    )
    if looks_pathlike:
        node, _tried = _resolve_uid(be, candidate)
        if node is not None and (kinds_set is None or node.kind in kinds_set):
            candidates.append(node)
            strategy = "path_resolve"

    # Strategy 3: FTS5 — only when path-resolve missed.
    if not candidates:
        sqlite_conn = getattr(be, "_conn", None)
        if sqlite_conn is not None:
            try:
                fts_q = _fts5_safe_query(candidate)
                if fts_q:
                    rows = sqlite_conn.execute(
                        """
                        SELECT n.uid, n.kind, n.label, n.file_path, n.start_line,
                               n.end_line, n.signature, n.lang, n.doc_blob,
                               n.ast_hash, n.content_hash, n.metadata_json
                        FROM graph_nodes_fts
                        JOIN graph_nodes n ON n.id = graph_nodes_fts.rowid
                        WHERE graph_nodes_fts MATCH ?
                        ORDER BY rank
                        LIMIT ?
                        """,
                        (fts_q, int(top) * 3),
                    ).fetchall()
                    row_to_node = getattr(be, "_row_to_node", None)
                    for row in rows:
                        node = row_to_node(row) if row_to_node else None
                        if node is None:
                            continue
                        if kinds_set is not None and node.kind not in kinds_set:
                            continue
                        candidates.append(node)
                        if len(candidates) >= int(top):
                            break
                    if candidates and not strategy:
                        strategy = "fts5"
            except Exception as exc:
                logger.debug("fts5 resolve suppressed: %s", exc)

    # Strategy 4 (fallback): plain lexical search — last resort.
    if not candidates:
        candidates = _lexical_search(
            be,
            q=candidate,
            kinds=tuple(kinds) if kinds else None,
            limit=int(top),
            max_hops=1,
        )
        if candidates:
            strategy = "lexical_like"

    results = [
        {
            **NodeSummary.from_node(n).to_dict(),
            "confidence": 1.0 if strategy == "path_resolve" else 0.7,
        }
        for n in candidates[:top]
    ]
    return _ok(
        {"results": results, "strategy": strategy or "miss"},
        meta={"backend": be.backend_id, "query": candidate[:200]},
    )


def _fts5_safe_query(raw: str) -> str:
    """Sanitise a free-text query for FTS5.

    FTS5 reserves `"`, `*`, `(`, `)`, `:`. We strip them rather than
    quote-escape because most agent queries are noun phrases — splitting
    into tokens with implicit AND is the highest-recall behaviour.
    Returns empty string on degenerate input so the caller skips FTS.
    """
    cleaned = []
    for ch in raw:
        if ch.isalnum() or ch in "._-":
            cleaned.append(ch)
        else:
            cleaned.append(" ")
    tokens = [t for t in "".join(cleaned).split() if len(t) >= 2]
    if not tokens:
        return ""
    # Quote each token to handle digits + dotted names; join with space
    # so FTS5 applies an implicit AND.
    return " ".join(f'"{t}"' for t in tokens[:8])


__all__ = [
    "cos_graph_centrality",
    "cos_graph_communities",
    "cos_graph_context",
    "cos_graph_contracts",
    "cos_graph_detect_changes",
    "cos_graph_doctor",
    "cos_graph_entrypoints",
    "cos_graph_export",
    "cos_graph_impact",
    "cos_graph_path",
    "cos_graph_query",
    "cos_graph_ranking",
    "cos_graph_references",
    "cos_graph_rename_plan",
    "cos_graph_resolve",
    "cos_graph_similar",
    "cos_graph_trace",
    "reset_backend",
]
