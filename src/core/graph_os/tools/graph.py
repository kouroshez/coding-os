"""graph_os — the cos_graph_* MCP tool implementations.

DEPENDS:  graph_os.types, graph_os.backend, graph_os.backends.*.
"""

from __future__ import annotations

import os
import threading
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from ..backend import (
    BackendUnavailable as BackendUnavailable,
    GraphBackend as GraphBackend,
    get_backend as get_backend,
)
from ..types import (
    GraphNode as GraphNode,
)
from ._graph_envelope import (
    _TELEMETRY_MAX_BYTES as _TELEMETRY_MAX_BYTES,
    _TELEMETRY_PATH_CACHE as _TELEMETRY_PATH_CACHE,
    _emit_telemetry as _emit_telemetry,
    _envelope_module as _envelope_module,
    _fail as _fail,
    _file_disk_hash as _file_disk_hash,
    _file_freshness as _file_freshness,
    _graph_marker_dir as _graph_marker_dir,
    _ok as _ok,
    _rotate_telemetry_atomically as _rotate_telemetry_atomically,
    _telemetry_path as _telemetry_path,
    _touch_session_marker as _touch_session_marker,
    _validate_confidence as _validate_confidence,
    _validate_min_chars as _validate_min_chars,
    _validate_non_negative_int as _validate_non_negative_int,
    _validate_positive_int as _validate_positive_int,
    _write_consult_marker as _write_consult_marker,
    logger as logger,
)
from ._graph_lookup import (
    _HARAKAT_STRIP as _HARAKAT_STRIP,
    _KIND_RESOLVE_RANK as _KIND_RESOLVE_RANK,
    _KIND_RESOLVE_WEIGHT as _KIND_RESOLVE_WEIGHT,
    _UID_FORMAT_HINT as _UID_FORMAT_HINT,
    _UID_PATH_PREFIXES as _UID_PATH_PREFIXES,
    _fail_uid_not_found as _fail_uid_not_found,
    _fold_harakat as _fold_harakat,
    _fts5_label_lookup as _fts5_label_lookup,
    _fts5_safe_query as _fts5_safe_query,
    _lexical_search as _lexical_search,
    _looks_like_label as _looks_like_label,
    _looks_prefixed as _looks_prefixed,
    _normalize_kinds as _normalize_kinds,
    _resolve_uid as _resolve_uid,
)
from ._graph_walk import (
    _BEHAVIOURAL_EDGE_TYPES as _BEHAVIOURAL_EDGE_TYPES,
    _SEMANTIC_EDGES as _SEMANTIC_EDGES,
    NodeSummary as NodeSummary,
    _bulk_nodes as _bulk_nodes,
    _contains_ancestors as _contains_ancestors,
    _count_edges_for as _count_edges_for,
    _degree_map_for as _degree_map_for,
    _edge_to_dict as _edge_to_dict,
    _walk_bfs as _walk_bfs,
)

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
from ._graph_centrality import cos_graph_centrality  # noqa: E402

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
from ._graph_hygiene import (  # noqa: E402, F401
    cos_graph_dead_code,
    cos_graph_test_gap,
)
from ._graph_insights import (  # noqa: E402, F401
    cos_graph_communities,
    cos_graph_cycles,
    cos_graph_entrypoints,
)
from ._graph_paths import (  # noqa: E402
    cos_graph_path,
    cos_graph_trace,
)
from ._graph_ranking import cos_graph_ranking  # noqa: E402
from ._graph_read import (  # noqa: E402
    cos_graph_context,
    cos_graph_query,
)
from ._graph_references import cos_graph_references  # noqa: E402
from ._graph_similar import (  # noqa: E402, F401
    cos_graph_search,
    cos_graph_similar,
)
