"""graph_os — the cos_graph_* MCP tool implementations.

DEPENDS:  graph_os.types, graph_os.backend, graph_os.backends.*.
"""

from __future__ import annotations

import contextlib
import difflib
import hashlib
import json
import logging
import os
import sys
import threading
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..backend import BackendUnavailable, GraphBackend, get_backend
from ..types import GraphEdge, GraphNode

# F5 staleness guard — capture this module's mtime at import. A long-running
# MCP server never hot-reloads; when graph.py on disk is edited after boot the
# server keeps serving stale code (a primary-tool crash that looks like a graph
# bug). cos_graph_doctor surfaces _server_stale() so the agent restarts instead
# of trusting a fossil. Self-contained: catches edits to this file (the F5 case).
try:
    _MODULE_LOADED_MTIME = os.path.getmtime(__file__)
except OSError:
    _MODULE_LOADED_MTIME = 0.0


def _server_stale() -> bool:
    if not _MODULE_LOADED_MTIME:
        return False
    try:
        return os.path.getmtime(__file__) > _MODULE_LOADED_MTIME + 1.0
    except OSError:
        return False


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


def _file_disk_hash(file_path: str) -> str | None:
    try:
        content = Path(file_path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def _graph_marker_dir() -> Path:
    # Agent-scoped, not panel-scoped: the shared MCP server resolves
    # COS_AGENT_DIR but never the calling tab's panel. The content_hash
    # binding below is what makes the wider scope safe — a marker counts
    # only while the consulted content still matches disk, whoever read it.
    agent_dir = os.environ.get("COS_AGENT_DIR")
    if not agent_dir:
        state_dir = os.environ.get("COS_STATE_DIR") or ".coding-os"
        agent = os.environ.get("COS_AGENT") or "claude"
        agent_dir = f"{state_dir}/{agent}"
    return Path(agent_dir) / ".graph"


def _write_consult_marker(name: str, payload: dict[str, Any]) -> None:
    try:
        marker_dir = _graph_marker_dir()
        marker_dir.mkdir(parents=True, exist_ok=True)
        (marker_dir / name).write_text(json.dumps(payload), encoding="utf-8")
    except OSError as exc:
        logger.debug("graph consult marker failed: %s", exc)


def _file_freshness(backend_obj: GraphBackend, file_path: str | None) -> dict[str, Any] | None:
    if not file_path:
        return None
    disk = _file_disk_hash(file_path)
    file_node = backend_obj.get_node(f"code:file:{file_path}")
    indexed = file_node.content_hash if file_node else None
    if disk is None or indexed is None:
        return None
    return {"stale": disk != indexed, "disk_hash": disk, "indexed_hash": indexed}


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


def _validate_positive_int(value: Any, field: str) -> Any:
    if not isinstance(value, int) or value <= 0:
        return _fail("validation", f"{field} must be a positive int (got {value!r})")
    return None


def _validate_non_negative_int(value: Any, field: str) -> Any:
    if not isinstance(value, int) or value < 0:
        return _fail("validation", f"{field} must be >= 0 (got {value!r})")
    return None


def _validate_confidence(value: Any, field: str) -> Any:
    # W7.1 / R4-19/R4-26: confidence is in [0.0, 1.0]; impact + query
    # silently accepted 999 and filtered everything.
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return _fail("validation", f"{field} must be a number (got {type(value).__name__})")
    if value < 0.0 or value > 1.0:
        return _fail("validation", f"{field} must be in [0.0, 1.0] (got {value})")
    return None


def _validate_min_chars(value: Any, field: str, *, min_chars: int = 2) -> Any:
    # W7.1 / R4-09: cos_graph_query enforces 2-char min; cos_graph_resolve
    # silently accepted single-char fuzzy. Parity.
    if not isinstance(value, str):
        return _fail("validation", f"{field} must be a string (got {type(value).__name__})")
    if len(value.strip()) < min_chars:
        return _fail("validation", f"{field} must be at least {min_chars} chars")
    return None


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
        with contextlib.suppress(OSError):
            os.unlink(tmp)


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

# F4 / F2 / shared: edge types that represent *behavioural* dependency
# (a real call / construction / dispatch / import) — promoting a
# behavioural edge to `will_break` in impact analysis, or counting it
# as a usage site in rename planning. Structural edges (`contains`,
# `tested_by`) are deliberately excluded. Single SSOT shared by
# `cos_graph_impact`, `cos_graph_rename_plan`, and any future tier
# logic — keeps the three call sites in lockstep.
_BEHAVIOURAL_EDGE_TYPES: frozenset[str] = frozenset(
    {
        "calls",
        "imports",
        "constructs",
        "accesses_field",
        "has_param_type",
        "has_return_type",
        "returns_type",
        "inherits_from",
        "implements",
        "dispatches",
        "awaits",
        "is_decorated_by",
        "handles_route",
        "handles_event",
        "handles_tool",
        "references_doc",
    }
)


# G8/G9/G39: kind-weighting for resolve / context / query — real
# symbols rank above imports + external stubs at the same FTS5 score.
_KIND_RESOLVE_WEIGHT: dict[str, int] = {
    "class": 1,
    "code:class": 1,
    "function": 2,
    "code:function": 2,
    "method": 3,
    "code:method": 3,
    "interface": 4,
    "code:interface": 4,
    "variable": 5,
    "code:variable": 5,
    "mcp_tool": 6,
    "hook": 6,
    "tool": 6,
    "route": 6,
    "module": 10,
    "code:module": 10,
    "file": 11,
    "code:file": 11,
    "doc:file": 12,
    "doc:heading": 13,
    "import_": 20,
    "code:import": 20,
    "identifier": 30,  # `code:external:unresolved:*` lives here
}


def _KIND_RESOLVE_RANK(node: GraphNode) -> tuple[int, int]:
    """Lower tuple == better. Tie-break by uid length (shorter is canonical)."""
    weight = _KIND_RESOLVE_WEIGHT.get(node.kind or "", 25)
    if (node.uid or "").startswith("code:external:"):
        weight += 5
    return (weight, len(node.uid or ""))


def _normalize_kinds(kinds: Any) -> tuple[str, ...]:
    # G3: FastMCP wire can deliver Sequence[str] as stringified JSON.
    # Accept list/CSV/JSON-array-string/single-stringified-list.
    if kinds is None:
        return ()
    if isinstance(kinds, str):
        s = kinds.strip()
        if not s:
            return ()
        if s.startswith("[") and s.endswith("]"):
            try:
                import json as _json

                parsed = _json.loads(s)
                if isinstance(parsed, list):
                    return tuple(str(x).strip() for x in parsed if str(x).strip())
            except (_json.JSONDecodeError, TypeError, ValueError):
                pass  # not JSON → fall through to the CSV split below (intentional)
        return tuple(p.strip() for p in s.split(",") if p.strip())
    if isinstance(kinds, (list, tuple)):
        if len(kinds) == 1 and isinstance(kinds[0], str) and kinds[0].lstrip().startswith("["):
            return _normalize_kinds(kinds[0])
        return tuple(str(k).strip() for k in kinds if str(k).strip())
    return ()


def _looks_prefixed(raw: str) -> bool:
    """True when input already carries an explicit uid scheme."""
    head = raw.split("/", 1)[0]
    return ":" in head


def _resolve_uid(backend: GraphBackend, raw_uid: str) -> tuple[GraphNode | None, list[str], str]:
    """Look up a node uid, with path-prefix fallback for raw paths.

    Returns ``(node, tried, source)`` where ``tried`` is the ordered list
    of candidates attempted and ``source`` is one of ``direct`` |
    ``path_prefix`` | ``fuzzy_fts5`` | ``not_found``.

    R4-01: bare identifiers used to silently fall through to FTS5 fuzzy
    and return a plausible-but-wrong symbol. After fix, FTS5 fallback
    fires only for identifier-shaped inputs (``_looks_like_label``) and
    callers surface ``meta.resolved_from="fuzzy_fts5"`` so the agent can
    tell the answer came from a fuzzy match instead of an explicit lookup.
    """
    direct = backend.get_node(raw_uid)
    if direct is not None:
        return direct, [raw_uid], "direct"

    if _looks_prefixed(raw_uid):
        return None, [raw_uid], "not_found"

    tried: list[str] = [raw_uid]
    for prefix in _UID_PATH_PREFIXES:
        candidate = f"{prefix}{raw_uid}"
        tried.append(candidate)
        node = backend.get_node(candidate)
        if node is not None:
            return node, tried, "path_prefix"

    if _looks_like_label(raw_uid):
        fts_node = _fts5_label_lookup(backend, raw_uid)
        if fts_node is not None:
            tried.append(f"fts5:{raw_uid}")
            return fts_node, tried, "fuzzy_fts5"
    return None, tried, "not_found"


def _looks_like_label(raw: str) -> bool:
    if len(raw) < 3:
        return False
    if not any(c.isalpha() for c in raw):
        return False
    return all(c.isalnum() or c in "_." for c in raw)


def _fts5_label_lookup(backend: GraphBackend, raw_label: str) -> GraphNode | None:
    """Pick the top-ranked FTS5 hit whose label matches `raw_label`."""
    sqlite_conn = getattr(backend, "_conn", None)
    if sqlite_conn is None:
        return None
    row_to_node = getattr(backend, "_row_to_node", None)
    if row_to_node is None:
        return None
    fts_q = _fts5_safe_query(raw_label)
    if not fts_q:
        return None
    try:
        rows = sqlite_conn.execute(
            """
            SELECT n.kind, n.label, n.uid, n.file_path, n.start_line,
                   n.end_line, n.signature, n.lang, n.doc_blob,
                   n.ast_hash, n.content_hash, n.metadata_json
            FROM graph_nodes_fts
            JOIN graph_nodes n ON n.id = graph_nodes_fts.rowid
            WHERE graph_nodes_fts MATCH ?
            ORDER BY rank
            LIMIT 20
            """,
            (fts_q,),
        ).fetchall()
    except Exception as exc:
        logger.debug("fts5 resolve fallback suppressed: %s", exc)
        return None
    # Prefer an exact label match if FTS5 surfaces one; otherwise take
    # the top-ranked hit so a near-match still resolves.
    # G9: rank candidates by kind weight (real symbol > doc heading >
    # import > external) — F11 fallback used to return whatever FTS5
    # ranked first, including doc:heading when caller wanted code:function.
    nodes = [row_to_node(r) for r in rows]
    nodes = [n for n in nodes if n is not None]
    for n in nodes:
        if (n.label or "") == raw_label and not (n.uid or "").startswith("code:external:"):
            return n
    if nodes:
        return sorted(nodes, key=_KIND_RESOLVE_RANK)[0]
    return None


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
        # Split the OR-join into two index-friendly halves (the OR forced a full
        # edge scan, bypassing idx_graph_edges_source/target). UNION ALL + outer
        # GROUP BY sums in- and out-degree per uid. TASK-228.
        rows = sqlite_conn.execute(
            f"""
            SELECT uid, SUM(cnt) FROM (
                SELECT n.uid AS uid, COUNT(*) AS cnt
                FROM graph_edges_v12 e JOIN graph_nodes n ON n.id = e.source_id
                WHERE n.uid IN ({placeholders}) GROUP BY n.uid
                UNION ALL
                SELECT n.uid AS uid, COUNT(*) AS cnt
                FROM graph_edges_v12 e JOIN graph_nodes n ON n.id = e.target_id
                WHERE n.uid IN ({placeholders}) GROUP BY n.uid
            ) GROUP BY uid
            """,
            tuple(uids) + tuple(uids),
        ).fetchall()
    except Exception as exc:
        logger.debug("degree query suppressed: %s", exc)
        return {}
    return {row[0]: int(row[1]) for row in rows}


def _edge_to_dict(edge: GraphEdge, *, include_evidence: bool = False) -> dict[str, Any]:
    # surface provenance derived from extractor — additive,
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
    exclude_kinds: frozenset[str] = frozenset(),
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
            for edge, next_uid in zip(frontier_edges, frontier_uids, strict=False):
                node = fetched.get(next_uid)
                if node is None:
                    continue
                # TASK-403: skip excluded (noise) kinds DURING the walk so
                # they never consume the visit budget — the export used to
                # over-fetch 4× to compensate post-hoc, which quadrupled
                # rooted-walk latency.
                if exclude_kinds and (node.kind or "") in exclude_kinds:
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


# edge categories that drive the new view modes.
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
                    (*list(kinds), int(limit) * 6),
                ).fetchall()
            else:
                # F13: try the maintained FTS5 index first (indexed MATCH,
                # scales to 500k); fall back to the leading-wildcard LIKE
                # scan only when FTS5 yields nothing so recall is preserved.
                fts_q = _fts5_safe_query(lower)
                if fts_q:
                    try:
                        fts_kinds_clause = ""
                        fts_params: list[Any] = [fts_q]
                        if kinds:
                            ph = ",".join(["?"] * len(kinds))
                            fts_kinds_clause = f" AND n.kind IN ({ph})"
                            fts_params.extend(list(kinds))
                        fts_params.append(int(limit) * 6)
                        rows = sqlite_conn.execute(
                            f"""
                            SELECT n.kind, n.label, n.uid, n.file_path, n.start_line,
                                   n.end_line, n.signature, n.lang, n.doc_blob,
                                   n.ast_hash, n.content_hash, n.metadata_json
                            FROM graph_nodes_fts
                            JOIN graph_nodes n ON n.id = graph_nodes_fts.rowid
                            WHERE graph_nodes_fts MATCH ?{fts_kinds_clause}
                            LIMIT ?
                            """,
                            tuple(fts_params),
                        ).fetchall()
                    except Exception as exc:
                        logger.debug("fts5 lexical search suppressed: %s", exc)
                        rows = []
                if not rows:
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
        # G39: penalise external stubs + identifier noise so they don't
        # outrank a real symbol at the same label match.
        kind_penalty = 0.0
        if (n.uid or "").startswith("code:external:"):
            kind_penalty = 0.5
        elif n.kind == "identifier":
            kind_penalty = 0.4
        elif (n.kind or "") in ("import_", "code:import"):
            kind_penalty = 0.2
        return base + min(boost, 0.4) - kind_penalty

    return sorted(candidates, key=score, reverse=True)[:limit]


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
    # W7.1 / R4-09: parity with cos_graph_query — both require q>=2 chars.
    err = _validate_min_chars(q, "q", min_chars=2)
    if err:
        return err
    err = _validate_positive_int(top, "top")
    if err:
        return err
    try:
        be = _backend(backend=backend)
    except BackendUnavailable as exc:
        return _fail("unavailable", str(exc), retryable=True)

    candidate = q.strip()
    # G3: normalize kinds (wire trap)
    parsed_kinds = _normalize_kinds(kinds)
    kinds_set = set(parsed_kinds) if parsed_kinds else None
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
        node, _tried, _src = _resolve_uid(be, candidate)
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
                        SELECT n.kind, n.label, n.uid, n.file_path, n.start_line,
                               n.end_line, n.signature, n.lang, n.doc_blob,
                               n.ast_hash, n.content_hash, n.metadata_json
                        FROM graph_nodes_fts
                        JOIN graph_nodes n ON n.id = graph_nodes_fts.rowid
                        WHERE graph_nodes_fts MATCH ?
                        ORDER BY rank
                        LIMIT ?
                        """,
                        (fts_q, int(top) * 6),
                    ).fetchall()
                    row_to_node = getattr(be, "_row_to_node", None)
                    pool: list[GraphNode] = []
                    for row in rows:
                        node = row_to_node(row) if row_to_node else None
                        if node is None:
                            continue
                        if kinds_set is not None and node.kind not in kinds_set:
                            continue
                        pool.append(node)
                    # G8: weight by kind preference — real symbols beat
                    # imports + external stubs at the same FTS5 rank.
                    candidates.extend(sorted(pool, key=_KIND_RESOLVE_RANK)[: int(top)])
                    if candidates and not strategy:
                        strategy = "fts5"
            except Exception as exc:
                logger.debug("fts5 resolve suppressed: %s", exc)

    # Strategy 4 (fallback): plain lexical search — last resort.
    if not candidates:
        candidates = _lexical_search(
            be,
            q=candidate,
            kinds=parsed_kinds if parsed_kinds else None,
            limit=int(top),
            max_hops=1,
        )
        if candidates:
            strategy = "lexical_like"

    # F5: rank-decayed confidence so FTS5 / lexical hits are discriminated
    # by position (the obvious answer outranks the 10th) instead of a flat
    # 0.7. path_resolve stays a certain 1.0.
    results = [
        {
            **NodeSummary.from_node(n).to_dict(),
            "confidence": (
                1.0 if strategy == "path_resolve" else round(max(0.4, 0.9 - 0.05 * idx), 3)
            ),
        }
        for idx, n in enumerate(candidates[:top])
    ]
    return _ok(
        {"results": results, "strategy": strategy or "miss"},
        meta={"backend": be.backend_id, "query": candidate[:200]},
    )


# Arabic/Persian harakat — combining vowel + gemination marks (U+064B–U+0652)
# plus the superscript alef (U+0670). The unicode61 `remove_diacritics 2`
# tokenizer folds Latin combining marks but NOT these, so a harakat-bearing
# query would miss a harakat-free indexed form. Strip them from the query so
# the common case (harakat-typed query vs harakat-free index) matches. Full
# symmetric folding of harakat-bearing INDEXED text needs an FTS-rebuild
# migration and is deferred until Persian/Arabic is a named market (TASK-485).
_HARAKAT_STRIP = dict.fromkeys((*range(1611, 1619), 1648))


def _fold_harakat(raw: str) -> str:
    """Drop Arabic/Persian harakat so a vowel-marked query folds to its base."""
    return raw.translate(_HARAKAT_STRIP)


def _fts5_safe_query(raw: str) -> str:
    """Sanitise a free-text query for FTS5.

    FTS5 reserves `"`, `*`, `(`, `)`, `:`. We strip them rather than
    quote-escape because most agent queries are noun phrases — splitting
    into tokens with implicit AND is the highest-recall behaviour.
    Arabic/Persian harakat are folded first (see _fold_harakat).
    Returns empty string on degenerate input so the caller skips FTS.
    """
    raw = _fold_harakat(raw)
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


# Re-exported tool families — this module stays the single public surface
# (and the monkeypatch target); the sibling _graph_* modules are private.
from ._graph_analysis import (  # noqa: E402, F401
    _grep_string_literals,
    cos_graph_contracts,
    cos_graph_detect_changes,
    cos_graph_diff,
    cos_graph_impact,
    cos_graph_rename_plan,
)

# Re-exported so `from graph_os.tools.graph import cos_graph_doctor` keeps
# resolving after the split (the MCP wrapper and the CLI both use that path).
from ._graph_doctor import (  # noqa: E402, F401
    _current_extractor_ids,
    _is_phantom_orphan,
    cos_graph_doctor,
)
from ._graph_export import (  # noqa: E402, F401
    _AUTO_BLEND_BUCKETS,
    _CONTAINS_EDGES,
    _DEFAULT_NOISE_KINDS,
    _KNOWN_EDGE_TYPES,
    _escape,
    _safe_id,
    cos_graph_export,
)
from ._graph_insights import (  # noqa: E402, F401
    cos_graph_centrality,
    cos_graph_communities,
    cos_graph_cycles,
    cos_graph_dead_code,
    cos_graph_entrypoints,
    cos_graph_ranking,
    cos_graph_test_gap,
)
from ._graph_read import (  # noqa: E402, F401
    cos_graph_context,
    cos_graph_path,
    cos_graph_query,
    cos_graph_references,
    cos_graph_search,
    cos_graph_similar,
    cos_graph_trace,
)
