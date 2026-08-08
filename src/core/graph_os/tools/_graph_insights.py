"""Insight tools: entrypoints, communities, centrality, cycles, test_gap, dead_code, ranking.

Private module of graph_os.tools.graph — import via the graph module,
never directly (the kernel imports this file at its bottom).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from ..backend import BackendUnavailable
from . import graph as _kernel
from .graph import (
    _BEHAVIOURAL_EDGE_TYPES,
    _fail,
    _ok,
    _validate_positive_int,
    logger,
)


# G36: graph.py local validators wrap _fail so telemetry fires on
# validation failures too. _shared.py exposes the same helpers for
# board_os / thinking_os tools that don't need the telemetry layer.
def _validate_enum(value: Any, allowed: tuple[str, ...], field: str) -> Any:
    if value not in allowed:
        return _fail("validation", f"{field} must be one of {allowed} (got {value!r})")
    return None


def _clamp_int(value: int, *, min_v: int, max_v: int) -> tuple[int, bool]:
    clamped = max(min_v, min(int(value), max_v))
    return clamped, clamped != value


# F7b: prefix-noise tokens that pollute uid-based personalisation. Drop
# from the haystack so ranking queries like "function" / "src" don't
# spuriously match every node. Lowercase comparison.
_UID_PREFIX_NOISE_TOKENS: frozenset[str] = frozenset(
    {
        "code",
        "doc",
        "folder",
        "cos",
        "external",
        "unresolved",
        "file",
        "function",
        "class",
        "method",
        "module",
        "heading",
        "mcp_tool",
        "route",
        "frontmatter",
        "interface",
        "variable",
        "src",
    }
)

# G6/G7: stdlib + common third-party module names that pollute the
# centrality / ranking output when not excluded. Project-internal
# modules (`core.thinking_os.server` etc.) stay in scope.
_NOISE_MODULE_NAMES: frozenset[str] = frozenset(
    {
        "__future__",
        "abc",
        "argparse",
        "ast",
        "asyncio",
        "base64",
        "builtins",
        "collections",
        "concurrent",
        "contextlib",
        "copy",
        "csv",
        "dataclasses",
        "datetime",
        "decimal",
        "difflib",
        "enum",
        "functools",
        "glob",
        "hashlib",
        "heapq",
        "http",
        "importlib",
        "inspect",
        "io",
        "ipaddress",
        "itertools",
        "json",
        "logging",
        "math",
        "multiprocessing",
        "operator",
        "os",
        "pathlib",
        "pickle",
        "platform",
        "pprint",
        "queue",
        "random",
        "re",
        "secrets",
        "select",
        "shutil",
        "signal",
        "socket",
        "sqlite3",
        "stat",
        "string",
        "struct",
        "subprocess",
        "sys",
        "tempfile",
        "textwrap",
        "threading",
        "time",
        "tomllib",
        "traceback",
        "types",
        "typing",
        "unittest",
        "urllib",
        "uuid",
        "warnings",
        "weakref",
        "xml",
        "yaml",
        "zipfile",
        # very common third-party that pollutes hubs
        "pytest",
        "click",
        "anyio",
        "httpx",
        "pydantic",
        "fastapi",
        "requests",
        "numpy",
    }
)

# Largest IN-list chunk — stays well under SQLite's default variable cap so the
# batched edge scans below work on every SQLite build.
_EDGE_SCAN_CHUNK = 900


def _edges_among(sqlite_conn, node_ids: Sequence[int]) -> list[tuple[int, int, str]]:
    """All edges whose SOURCE id is in node_ids, fetched in indexed chunks.

    Returns (source_id, target_id, edge_type) rows. Target-side filtering (both
    endpoints in the set) is left to the caller. Replaces both the betweenness
    per-node query storm and ranking's unscoped LIMIT scan with one indexed
    query per chunk. TASK-228.
    """
    ids = list(node_ids)
    out: list[tuple[int, int, str]] = []
    for i in range(0, len(ids), _EDGE_SCAN_CHUNK):
        chunk = ids[i : i + _EDGE_SCAN_CHUNK]
        ph = ",".join("?" * len(chunk))
        out.extend(
            sqlite_conn.execute(
                f"SELECT source_id, target_id, edge_type FROM graph_edges_v12 "
                f"WHERE source_id IN ({ph})",
                tuple(chunk),
            ).fetchall()
        )
    return out


def cos_graph_entrypoints(
    *,
    top: int = 20,
    kind: str | None = None,
    min_score: float = 0.05,
    diversify: bool = True,
    backend: str | None = None,
) -> dict[str, Any]:
    """Return scored entry-point candidates (TASK-081).

    F10 / Audit #13: many real entrypoints tie at the same score and
    the pre-fix `sort(-score, uid)` made the alphabetically-first file
    monopolise the top-N. `diversify=True` (default) round-robins
    across distinct file_paths within each score tier so the top
    surfaces structurally different entrypoints. Set False to recover
    the raw score-only ranking.
    """
    err = _validate_positive_int(top, "top")
    if err:
        return err
    top, _ = _clamp_int(top, min_v=1, max_v=200)
    if kind is not None:
        err = _validate_enum(kind, ("main", "cli", "http", "cron", "test"), "kind")
        if err:
            return err
    try:
        be = _kernel._backend(backend=backend)
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
    # G20: rank cli/http/mcp/cron above tests. Audit showed top-10
    # ALL tests at the 0.85 tied score, with main()/CLI never visible.
    _KIND_PRIORITY = {
        "main": 4,
        "cli": 4,
        "http": 3,
        "cron": 2,
        "test": 1,
    }
    eps = sorted(
        eps,
        key=lambda ep: (
            -_KIND_PRIORITY.get(getattr(ep, "kind", ""), 0),
            -float(getattr(ep, "score", 0.0)),
        ),
    )
    total = len(eps)
    if diversify and eps:
        # Round-robin by file_path within each score-tier so the top-N
        # spans multiple files. Pure sort would let one file's tests
        # all alphabetise to the front.
        from collections import defaultdict

        by_file: dict[str | None, list[Any]] = defaultdict(list)
        for ep in eps:
            by_file[ep.file_path].append(ep)
        # Stable interleave: pop one entry from each file bucket per
        # round until either top or all buckets are drained.
        ordered: list[Any] = []
        files_in_score_order: list[str | None] = []
        seen_files: set[str | None] = set()
        for ep in eps:
            if ep.file_path not in seen_files:
                seen_files.add(ep.file_path)
                files_in_score_order.append(ep.file_path)
        while len(ordered) < top:
            advanced = False
            for fp in files_in_score_order:
                if by_file[fp]:
                    ordered.append(by_file[fp].pop(0))
                    advanced = True
                    if len(ordered) >= top:
                        break
            if not advanced:
                break
        eps = ordered
    rows = [ep.to_dict() for ep in eps[:top]]
    return _ok(
        {"entrypoints": rows, "total_count": total},
        meta={
            "backend": be.backend_id,
            "count": len(rows),
            "scanned_kinds": ["code:function", "code:method", "function", "method"],
            "top": top,
            "result_truncated": total > top,
        },
    )


def cos_graph_communities(
    *,
    top: int = 50,
    min_size: int = 2,
    max_members: int = 10,
    backend: str | None = None,
) -> dict[str, Any]:
    """Return Louvain process clusters. Response payload key is `processes`.

    F8 / Audit #9: each process embeds its member nodes. On real repos
    a single process can hold 100+ members and `top=5` returned a
    236KB envelope that blew past the MCP token budget. `max_members`
    caps the inline list per process; `member_count` still reports the
    real size, and `members_truncated` flags when the slice is short.
    """
    err = _validate_positive_int(top, "top")
    if err:
        return err
    top, _ = _clamp_int(top, min_v=1, max_v=200)
    if not isinstance(min_size, int) or min_size < 1:
        return _fail("validation", "min_size must be >= 1")
    err = _validate_positive_int(max_members, "max_members")
    if err:
        return err
    max_members, _ = _clamp_int(max_members, min_v=1, max_v=500)
    try:
        be = _kernel._backend(backend=backend)
    except BackendUnavailable as exc:
        return _fail("unavailable", str(exc), retryable=True)

    from .. import communities as comm_mod

    all_communities, _membership = comm_mod.compute_communities(be, min_size=int(min_size))
    rows = comm_mod.communities_to_processes(all_communities, relevant_uids=None)
    capped: list[dict[str, Any]] = []
    members_truncated = False
    # P2: adaptive envelope cap. At top=50 × default max_members=10, the
    # envelope hit 47K tokens — well past the safe ~5K threshold. Project
    # rows × members and shrink max_members or top until under budget.
    _TOKEN_TARGET = 5000
    _TOKENS_PER_MEMBER = 90  # empirical average per member entry
    _TOKENS_PER_PROCESS_HEADER = 60
    projected_top = min(top, len(rows))
    effective_max_members = max_members
    projected = (
        projected_top * _TOKENS_PER_PROCESS_HEADER
        + projected_top * effective_max_members * _TOKENS_PER_MEMBER
    )
    if projected > _TOKEN_TARGET:
        # Never shrink members below 3 — a "community" of 1
        # member kills the concept. Drop tail communities instead, then
        # only as a last resort shrink members down to 3, then 1.
        _MEMBER_FLOOR = min(3, max_members)
        # Step 1: shrink members down to the floor (or requested, whichever
        # is smaller) at current projected_top.
        budget_per_process_for_members = max(
            0, (_TOKEN_TARGET - projected_top * _TOKENS_PER_PROCESS_HEADER)
        )
        if projected_top > 0:
            effective_max_members = max(
                _MEMBER_FLOOR,
                budget_per_process_for_members // (projected_top * _TOKENS_PER_MEMBER),
            )
        effective_max_members = min(effective_max_members, max_members)
        # Step 2: if still over budget, drop tail communities.
        while (
            projected_top > 1
            and projected_top
            * (_TOKENS_PER_PROCESS_HEADER + effective_max_members * _TOKENS_PER_MEMBER)
            > _TOKEN_TARGET
        ):
            projected_top -= 1
        # Step 3: last resort — even 1 community at floor doesn't fit.
        # Lower the floor (1 member is still better than 0 communities).
        while (
            projected_top > 0
            and projected_top
            * (_TOKENS_PER_PROCESS_HEADER + effective_max_members * _TOKENS_PER_MEMBER)
            > _TOKEN_TARGET
            and effective_max_members > 1
        ):
            effective_max_members -= 1
        members_truncated = effective_max_members < max_members
    for row in rows[:projected_top]:
        members = row.get("members") or []
        if len(members) > effective_max_members:
            members_truncated = True
            row = {**row, "members": members[:effective_max_members]}
        capped.append(row)
    payload_truncated = projected_top < min(top, len(rows))
    return _ok(
        {"processes": capped},
        meta={
            "backend": be.backend_id,
            "count": len(capped),
            "total": len(rows),
            # back-compat: keep `max_members` key (existing tests + UI)
            "max_members": effective_max_members,
            "max_members_effective": effective_max_members,
            "max_members_requested": max_members,
            "members_truncated": members_truncated,
            "envelope_truncated": payload_truncated,
            "input_truncated": comm_mod.subgraph_input_truncated(be),
            "top_effective": projected_top,
            "top_requested": top,
        },
    )


def cos_graph_centrality(
    *,
    top: int = 20,
    kind: str | None = None,
    metric: str = "degree",
    include_external: bool = False,
    include_structural: bool = False,
    backend: str | None = None,
) -> dict[str, Any]:
    """Hub detection via degree / in_degree / out_degree / betweenness centrality.

    F6 / Audit #10: `include_external` defaults to False so unresolved
    builtins (`code:external:unresolved:str/int/bool/len`) and stdlib
    stubs (`code:external:pathlib:Path`) do not crowd the top of the
    list. Set True to opt back into the raw ranking.

    TASK-046: `include_structural` defaults to False so degree counts only
    behavioural edges (calls/imports/constructs/…). Otherwise structural
    containment (`contains`/doc links) dominates — registry.yaml's 798
    `contains` children make it the #1 "hub", burying real code chokepoints.
    Set True for raw all-edge degree.
    """
    err = _validate_positive_int(top, "top")
    if err:
        return err
    top, _ = _clamp_int(top, min_v=1, max_v=200)
    err = _validate_enum(metric, ("degree", "in_degree", "out_degree", "betweenness"), "metric")
    if err:
        return err
    try:
        be = _kernel._backend(backend=backend)
    except BackendUnavailable as exc:
        return _fail("unavailable", str(exc), retryable=True)

    sqlite_conn = getattr(be, "_conn", None)
    truncated = False

    # W7 / R4-16: reject an unknown `kind` filter instead of silently
    # returning [] (a typo'd kind was indistinguishable from "no
    # high-degree nodes of this kind"). Normalize first so legacy
    # colon-prefixed kinds (`code:function`) canonicalise to `function`.
    if kind:
        try:
            from ..types import normalize_kind as _normalize_kind_enum

            kind = _normalize_kind_enum(kind).value
        except Exception:
            # TASK-423: validate against the canonical NodeKind enum, not the
            # kinds PRESENT in the DB. We only reach this branch when
            # normalize_kind rejected the value, i.e. it is a genuine typo; an
            # empty/sparse graph must still accept a VALID kind filter (which
            # normalizes successfully and never enters this branch).
            from ..types import NodeKind as _NodeKind

            return _fail(
                "validation",
                f"unknown kind {kind!r}; known: {sorted(k.value for k in _NodeKind)}",
            )

    if sqlite_conn is not None:
        try:
            where_parts: list[str] = []
            params: list[Any] = []
            if kind:
                where_parts.append("n.kind = ?")
                params.append(kind)
            if not include_external:
                where_parts.append("n.uid NOT LIKE 'code:external:%'")
                # G6: also drop stdlib module hubs (`code:module:__future__`,
                # `code:module:pathlib`, ...) — F6 only kicked external out.
                stdlib_placeholders = ",".join("?" * len(_NOISE_MODULE_NAMES))
                where_parts.append(f"n.uid NOT IN ({stdlib_placeholders})")
                params.extend(f"code:module:{name}" for name in _NOISE_MODULE_NAMES)
            kind_clause = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""

            # Degree over behavioural edges only by default. The
            # edge filter sits in the JOIN ON clause, so its params precede
            # the WHERE (kind/stdlib) params.
            edge_params: list[Any] = []
            edge_join = ""
            if not include_structural:
                beh = sorted(_BEHAVIOURAL_EDGE_TYPES)
                edge_join = f"AND e.edge_type IN ({','.join('?' * len(beh))})"
                edge_params = beh

            in_deg_rows = sqlite_conn.execute(
                f"""
                SELECT n.uid, n.kind, n.label, COUNT(e.id) AS cnt
                FROM graph_nodes n
                LEFT JOIN graph_edges_v12 e ON e.target_id = n.id {edge_join}
                {kind_clause}
                GROUP BY n.id
                """,
                tuple(edge_params + params),
            ).fetchall()
            out_deg_rows = sqlite_conn.execute(
                f"""
                SELECT n.uid, COUNT(e.id) AS cnt
                FROM graph_nodes n
                LEFT JOIN graph_edges_v12 e ON e.source_id = n.id {edge_join}
                {kind_clause}
                GROUP BY n.id
                """,
                tuple(edge_params + params),
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
            if not include_structural and edge.edge_type not in _BEHAVIOURAL_EDGE_TYPES:
                continue
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

    if metric in ("in_degree", "out_degree"):
        # F7: rank by pure in/out degree. The default `degree` uses
        # (in+out)/norm, which conflates fan-in with fan-out — a high-fan-OUT
        # leaf (e.g. a UI page importing many modules) outranks a true
        # chokepoint. metric=in_degree gives the genuine "most depended-upon"
        # ranking; out_degree gives "depends on the most".
        _denom = (N - 1) if N > 1 else 1
        for r in rows_out:
            r["centrality_score"] = round(r[metric] / _denom, 6)

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
            # Batch every edge among the capped node set via chunked indexed
            # queries instead of one list_edges per node (was O(n) queries at
            # scale). honour include_structural so path counts skip the
            # containment skeleton the degree pass excludes. TASK-228.
            id_ph = ",".join("?" * len(all_uids_list))
            id_rows = sqlite_conn.execute(
                f"SELECT id, uid FROM graph_nodes WHERE uid IN ({id_ph})",
                tuple(all_uids_list),
            ).fetchall()
            id_to_uid = dict(id_rows)
            for s_id, t_id, etype in _edges_among(sqlite_conn, list(id_to_uid)):
                if not include_structural and etype not in _BEHAVIOURAL_EDGE_TYPES:
                    continue
                i = uid_idx.get(id_to_uid.get(s_id))
                j = uid_idx.get(id_to_uid.get(t_id))
                if i is not None and j is not None:
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
            "result_truncated": truncated,
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


def cos_graph_cycles(
    *,
    scope: str = "imports",
    top: int = 20,
    min_size: int = 2,
    backend: str | None = None,
) -> dict[str, Any]:
    """Detect circular dependencies — strongly-connected components in the import (or call) graph."""
    err = _validate_positive_int(top, "top")
    if err:
        return err
    top, _ = _clamp_int(top, min_v=1, max_v=200)
    if scope not in ("imports", "calls"):
        return _fail("validation", "scope must be 'imports' or 'calls'")
    try:
        be = _kernel._backend(backend=backend)
    except BackendUnavailable as exc:
        return _fail("unavailable", str(exc), retryable=True)
    sqlite_conn = getattr(be, "_conn", None)
    if sqlite_conn is None:
        return _ok(
            {
                "cycles": [],
                "total_count": 0,
                "scope": scope,
                "note": "cycle detection requires the sqlite backend",
            },
            meta={"backend": be.backend_id, "layer": "graph"},
        )
    try:
        import networkx as nx
    except ImportError:
        return _fail("unavailable", "networkx required for cycle detection", retryable=False)

    # Bound the edge scan so cycle detection on a 1M+ call-edge graph stays in
    # memory; honest truncation flag tells the caller it was a bounded sample.
    _CYCLE_EDGE_CAP = 50000
    if scope == "imports":
        # module->module import edges. Stdlib/external modules are leaves
        # (no outbound in-repo import) so SCC naturally excludes them — any
        # SCC of size>=2 is a genuine circular module dependency.
        rows = sqlite_conn.execute(
            "SELECT s.uid, t.uid FROM graph_edges_v12 e "
            "JOIN graph_nodes s ON s.id=e.source_id JOIN graph_nodes t ON t.id=e.target_id "
            "WHERE e.edge_type='imports' AND s.kind IN ('module','code:module') "
            "AND t.kind IN ('module','code:module') LIMIT ?",
            (_CYCLE_EDGE_CAP,),
        ).fetchall()
    else:
        rows = sqlite_conn.execute(
            "SELECT s.uid, t.uid FROM graph_edges_v12 e "
            "JOIN graph_nodes s ON s.id=e.source_id JOIN graph_nodes t ON t.id=e.target_id "
            "WHERE e.edge_type='calls' AND s.uid NOT LIKE 'code:external:%' "
            "AND t.uid NOT LIKE 'code:external:%' AND s.id != t.id LIMIT ?",
            (_CYCLE_EDGE_CAP,),
        ).fetchall()
    edges_truncated = len(rows) >= _CYCLE_EDGE_CAP

    g = nx.DiGraph()
    g.add_edges_from(rows)
    sccs = [
        sorted(c) for c in nx.strongly_connected_components(g) if len(c) >= max(2, int(min_size))
    ]
    sccs.sort(key=len, reverse=True)
    cycles = [
        {"size": len(comp), "members": comp[:15], "members_truncated": len(comp) > 15}
        for comp in sccs[:top]
    ]
    return _ok(
        {
            "cycles": cycles,
            "total_count": len(sccs),
            "scope": scope,
            "note": (
                "each cycle = a strongly-connected component (mutually-reachable nodes); "
                "size>=2 = circular dependency. scope=imports is the module-level design "
                "smell; scope=calls includes legitimate mutual recursion."
            ),
        },
        meta={
            "backend": be.backend_id,
            "layer": "graph",
            "scope": scope,
            "result_truncated": len(sccs) > top or edges_truncated,
        },
    )


_DEAD_CODE_SKIP_LABELS = frozenset({"main", "register", "extract", "setup"})


def _is_test_file(fp: str) -> bool:
    return bool(fp) and (
        fp.startswith("tests/")
        or "/tests/" in fp
        or fp.startswith("test_")
        or "/test_" in fp
        or "_test." in fp
    )


def cos_graph_test_gap(
    *,
    kind: str = "",
    top: int = 50,
    backend: str | None = None,
) -> dict[str, Any]:
    """List prod function/method/class with zero inbound edge from any test (untested symbols)."""
    err = _validate_positive_int(top, "top")
    if err:
        return err
    top, _ = _clamp_int(top, min_v=1, max_v=500)
    try:
        be = _kernel._backend(backend=backend)
    except BackendUnavailable as exc:
        return _fail("unavailable", str(exc), retryable=True)
    sqlite_conn = getattr(be, "_conn", None)
    if sqlite_conn is None:
        return _ok(
            {"untested": [], "total_count": 0, "note": "test-gap scan requires the sqlite backend"},
            meta={"backend": be.backend_id, "layer": "graph"},
        )
    kinds: tuple[str, ...] = (
        "function",
        "method",
        "class",
        "code:function",
        "code:method",
        "code:class",
    )
    if kind:
        from ..types import normalize_kind as _normalize_kind_enum

        try:
            kn = _normalize_kind_enum(kind).value
        except Exception:
            return _fail("validation", f"unknown kind {kind!r}; use function|method|class")
        kinds = (kn, f"code:{kn}")

    ref_types = sorted(_BEHAVIOURAL_EDGE_TYPES)
    # Inbound edge counts ONLY when the source is a test file → symbols with
    # COUNT(s.id)=0 have no test exercising them (the inverse of dead_code).
    test_src = (
        "(s.file_path LIKE 'tests/%' OR s.file_path LIKE '%/tests/%' "
        "OR s.file_path LIKE 'test_%' OR s.file_path LIKE '%/test_%' "
        "OR s.file_path LIKE '%_test.%')"
    )
    edge_ph = ",".join("?" * len(ref_types))
    kind_ph = ",".join("?" * len(kinds))
    try:
        rows = sqlite_conn.execute(
            f"""
            SELECT n.uid, n.kind, n.label, n.file_path
            FROM graph_nodes n
            LEFT JOIN graph_edges_v12 e
              ON e.target_id = n.id AND e.edge_type IN ({edge_ph})
            LEFT JOIN graph_nodes s ON s.id = e.source_id AND {test_src}
            WHERE n.kind IN ({kind_ph})
              AND n.uid NOT LIKE 'code:external:%'
              AND n.file_path IS NOT NULL AND n.file_path != ''
            GROUP BY n.id
            HAVING COUNT(s.id) = 0
            """,
            (*ref_types, *kinds),
        ).fetchall()
    except Exception as exc:
        return _fail("internal", f"test-gap query failed: {exc}")

    untested: list[dict[str, Any]] = []
    for uid, nkind, label, fp in rows:
        lab = label or ""
        if _is_test_file(fp or ""):
            continue  # don't report test code itself as "untested"
        if lab.startswith("__") or lab in _DEAD_CODE_SKIP_LABELS:
            continue
        if (fp or "").endswith(".sh"):
            continue  # shell has no call-graph → cannot infer test coverage
        untested.append({"uid": uid, "kind": nkind, "label": lab, "file_path": fp})

    untested.sort(key=lambda d: (d["file_path"] or "", d["label"]))
    total = len(untested)
    return _ok(
        {
            "untested": untested[:top],
            "total_count": total,
            "note": (
                "candidates — symbols with no inbound edge from a test file. "
                "Indirect exercise (via CLI, fixtures, dynamic dispatch) may not "
                "show as an edge; shell excluded (no call-graph)."
            ),
        },
        meta={
            "backend": be.backend_id,
            "layer": "graph",
            "kind": kind or "function,method,class",
            "result_truncated": total > top,
        },
    )


def cos_graph_dead_code(
    *,
    kind: str = "",
    top: int = 50,
    include_tests: bool = False,
    backend: str | None = None,
) -> dict[str, Any]:
    """List in-repo symbols with zero non-test inbound references (dead-code candidates)."""
    err = _validate_positive_int(top, "top")
    if err:
        return err
    top, _ = _clamp_int(top, min_v=1, max_v=500)
    try:
        be = _kernel._backend(backend=backend)
    except BackendUnavailable as exc:
        return _fail("unavailable", str(exc), retryable=True)
    sqlite_conn = getattr(be, "_conn", None)
    if sqlite_conn is None:
        return _ok(
            {"dead": [], "total_count": 0, "note": "dead-code scan requires the sqlite backend"},
            meta={"backend": be.backend_id, "layer": "graph"},
        )

    kinds: tuple[str, ...] = (
        "function",
        "method",
        "class",
        "code:function",
        "code:method",
        "code:class",
    )
    if kind:
        from ..types import normalize_kind as _normalize_kind_enum

        try:
            kn = _normalize_kind_enum(kind).value
        except Exception:
            return _fail("validation", f"unknown kind {kind!r}; use function|method|class")
        kinds = (kn, f"code:{kn}")

    # "Referenced" = any inbound behavioural edge (calls/constructs/inherits/
    # implements/dispatches/handles_*/type-uses). handles_* means it is an
    # entry-point handler → not dead. Test-sourced edges are excluded so a
    # symbol used only by its own tests still surfaces as dead.
    ref_types = sorted(_BEHAVIOURAL_EDGE_TYPES)
    test_pred = (
        ""
        if include_tests
        else (
            " AND s.file_path IS NOT NULL"
            " AND s.file_path NOT LIKE 'tests/%' AND s.file_path NOT LIKE '%/tests/%'"
            " AND s.file_path NOT LIKE 'test_%' AND s.file_path NOT LIKE '%/test_%'"
            " AND s.file_path NOT LIKE '%_test.%'"
        )
    )
    edge_ph = ",".join("?" * len(ref_types))
    kind_ph = ",".join("?" * len(kinds))
    try:
        rows = sqlite_conn.execute(
            f"""
            SELECT n.uid, n.kind, n.label, n.file_path
            FROM graph_nodes n
            LEFT JOIN graph_edges_v12 e
              ON e.target_id = n.id AND e.edge_type IN ({edge_ph})
            LEFT JOIN graph_nodes s ON s.id = e.source_id{test_pred}
            WHERE n.kind IN ({kind_ph})
              AND n.uid NOT LIKE 'code:external:%'
              AND n.file_path IS NOT NULL AND n.file_path != ''
            GROUP BY n.id
            HAVING COUNT(s.id) = 0
            """,
            (*ref_types, *kinds),
        ).fetchall()
    except Exception as exc:
        return _fail("internal", f"dead-code query failed: {exc}")

    def _is_test_path(fp: str) -> bool:
        return bool(fp) and (
            fp.startswith("tests/")
            or "/tests/" in fp
            or fp.startswith("test_")
            or "/test_" in fp
            or "_test." in fp
        )

    dead: list[dict[str, Any]] = []
    for uid, nkind, label, fp in rows:
        lab = label or ""
        if lab.startswith("__") or lab in _DEAD_CODE_SKIP_LABELS:
            continue  # dunder + dynamic-dispatch entry points (register/extract/main/setup)
        # Shell has no intra-script call-graph (code_shell emits no `calls`
        # between bash functions), so every .sh function would look dead —
        # pure noise. Reachability needs a call-graph; skip languages w/o one.
        if (fp or "").endswith(".sh"):
            continue
        if not include_tests and _is_test_path(fp or ""):
            continue
        # Exception classes are caught / raised dynamically (`except FooError`,
        # `raise cls()`, registry lookup) — an AST "zero inbound edges" reading
        # is a false positive. PEP8 names them *Error/*Exception/*Warning; skip
        # rather than nag a delete that would break the handlers that catch them.
        if nkind in ("class", "code:class") and lab.endswith(("Error", "Exception", "Warning")):
            continue
        dead.append({"uid": uid, "kind": nkind, "label": lab, "file_path": fp})

    dead.sort(key=lambda d: (d["file_path"] or "", d["label"]))
    total = len(dead)
    return _ok(
        {
            "dead": dead[:top],
            "total_count": total,
            "note": (
                "candidates only — symbols reachable solely via dynamic dispatch, "
                "CLI/plugin registration, or external callers may appear here; "
                "verify with cos_graph_references before deleting"
            ),
        },
        meta={
            "backend": be.backend_id,
            "layer": "graph",
            "kind": kind or "function,method,class",
            "include_tests": include_tests,
            "result_truncated": total > top,
        },
    )


def cos_graph_ranking(
    *,
    query: str | None = None,
    top: int = 20,
    kind: str | None = None,
    damping: float = 0.85,
    iterations: int = 30,
    include_external: bool = False,
    include_tests: bool = False,
    backend: str | None = None,
) -> dict[str, Any]:
    """PageRank-based node ranking with optional query personalisation.

    F6 / Audit #11: `include_external=False` (default) excludes
    unresolved-stub + stdlib nodes (`code:external:*`) from the input
    set so the top of the ranking surfaces project-internal hubs
    instead of `__future__` / `pathlib` / builtins.
    """
    err = _validate_positive_int(top, "top")
    if err:
        return err
    top, _ = _clamp_int(top, min_v=1, max_v=200)
    if not (0.0 < damping < 1.0):
        return _fail("validation", "damping must be in (0, 1)")
    # W7.1 / R4-06: iterations=0 returned uniform vector with positive
    # rank_score that looked real. Reject as validation error.
    err = _validate_positive_int(iterations, "iterations")
    if err:
        return err
    try:
        be = _kernel._backend(backend=backend)
    except BackendUnavailable as exc:
        return _fail("unavailable", str(exc), retryable=True)

    _NODE_CAP = 5000
    truncated = False
    sqlite_conn = getattr(be, "_conn", None)

    if sqlite_conn is not None:
        try:
            where_parts: list[str] = []
            params_n: list[Any] = []
            if kind:
                where_parts.append("kind = ?")
                params_n.append(kind)
            if not include_external:
                where_parts.append("uid NOT LIKE 'code:external:%'")
                # G7: drop stdlib module hubs in line with G6 centrality.
                stdlib_placeholders = ",".join("?" * len(_NOISE_MODULE_NAMES))
                where_parts.append(f"uid NOT IN ({stdlib_placeholders})")
                params_n.extend(f"code:module:{name}" for name in _NOISE_MODULE_NAMES)
            if not include_tests:
                # Audit fix: test-fixture nodes (a helper called 60+ times
                # within one test file) dominated PageRank and buried every
                # production hub — top-20 was 100% tests/. Drop test-dir
                # nodes unless the caller explicitly opts in.
                where_parts.append(
                    "(file_path IS NULL OR (file_path NOT LIKE 'tests/%' "
                    "AND file_path NOT LIKE '%/tests/%'))"
                )
            kind_filter = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""
            params_n.append(_NODE_CAP)
            uid_rows = sqlite_conn.execute(
                f"SELECT id, uid, kind, label, file_path, start_line "
                f"FROM graph_nodes {kind_filter} LIMIT ?",
                tuple(params_n),
            ).fetchall()
            if len(uid_rows) >= _NODE_CAP:
                truncated = True
            # Scope the edge scan to the selected node set (chunked, indexed)
            # rather than a blunt unscoped LIMIT that both over-fetched
            # irrelevant edges and could miss in-set ones past the cap. TASK-228.
            edge_rows = _edges_among(sqlite_conn, [row[0] for row in uid_rows])
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
        for src, tgt, _etype in edge_rows:
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
        int_to_uid = dict(enumerate(node_ids_str))
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
    # F7 / Audit #12: previous matcher required the full query as a
    # substring of the label. "graph backend" matched no label literally
    # → empty vector → uniform teleport → identical to global PageRank.
    # Token-OR match: any whitespace-split token hits → seed weight ∝
    # token-hit count. Falls back to substring-AND when query has no
    # internal whitespace so single-name queries still target precisely.
    #
    # F7b: drop uid-prefix noise tokens (`code`, `function`, `module`,
    # `cos`, …) so a query like "function" or "src" does not spuriously
    # match every node via the uid string. Personalisation seed now
    # comes from content tokens only — label + uid-suffix words.
    personalized: dict[int, float] = {}
    if query:
        lower_q = query.lower().strip()
        tokens = [t for t in lower_q.split() if len(t) >= 2]
        if not tokens:
            tokens = [lower_q] if lower_q else []
        # F6: a generic structural doc_heading (Work Log / Read
        # First / …) carries no query relevance — but its uid PATH tokens
        # (e.g. a TASK file path containing "graph") used to seed it as if it
        # matched the query. Skip these, and weight LABEL hits far above
        # incidental PATH hits so a node whose NAME matches the query outranks
        # one that merely lives in a path containing the term.
        # Prefix-match (not exact) so template headings with suffixes match —
        # e.g. "Acceptance (G/W/T) — *this IS the Definition of Done*".
        # Skipping only removes the personalisation SEED; a genuinely relevant
        # heading can still rank via PageRank, so over-skip is cheap.
        _GENERIC_HEADINGS = (
            "work log",
            "read first",
            "acceptance",
            "notes",
            "see also",
            "overview",
            "summary",
            "background",
            "resume marker",
            "closing checklist",
            "source intent",
            "verification",
            "anti-patterns",
            "references",
            "repro steps",
            "source material",
            "findings register",
            "remediation",
        )
        for nid in node_ids:
            meta_entry = int_to_meta.get(nid)
            kind_n = (meta_entry[0] if meta_entry else "") or ""
            label = (meta_entry[1] if meta_entry else (int_to_uid.get(nid, ""))) or ""
            label_l = label.lower().strip()
            if "doc_heading" in kind_n and any(label_l.startswith(g) for g in _GENERIC_HEADINGS):
                continue
            uid_str = int_to_uid.get(nid, "")
            uid_content_tokens = [
                t
                for t in re.split(r"[^A-Za-z0-9]+", uid_str.lower())
                if t and t not in _UID_PREFIX_NOISE_TOKENS and len(t) >= 2
            ]
            label_hits = sum(1 for t in tokens if t in label_l)
            path_hits = sum(1 for t in tokens if t in " ".join(uid_content_tokens))
            score = label_hits * 3 + path_hits
            if score:
                personalized[nid] = float(score)
        total_p = sum(personalized.values())
        if total_p:
            personalized = {k: v / total_p for k, v in personalized.items()}

    # P1: precompute in_links ONCE — was recomputed O(N²) per iter
    # inside the rank loop (35.5s p99 → ~50ms expected at N=5000).
    in_links: dict[int, list[int]] = {}
    out_link_count: dict[int, int] = {}
    for src, tgts in out_links.items():
        out_link_count[src] = len(tgts)
        for tgt in tgts:
            in_links.setdefault(tgt, []).append(src)
    # Power iteration
    rank: dict[int, float] = dict.fromkeys(node_ids, 1.0 / N)
    dangling = {nid for nid in node_ids if not out_links.get(nid)}
    for _ in range(iterations):
        dangling_sum = sum(rank[nid] for nid in dangling) / N
        new_rank: dict[int, float] = {}
        for nid in node_ids:
            inbound = in_links.get(nid, [])
            push = sum(
                rank[src] / out_link_count[src] for src in inbound if out_link_count.get(src)
            )
            if personalized:
                teleport = personalized.get(nid, 0.0)
            else:
                teleport = 1.0 / N
            new_rank[nid] = (1 - damping) * teleport + damping * (push + dangling_sum)
        rank = new_rank

    results: list[dict[str, Any]] = []

    # Query-seeded nodes rank above generic PageRank hubs; no query → identical to global.
    def _rank_sort_key(item: tuple[int, float]) -> tuple[float, float]:
        nid, score = item
        seeded = 1.0 if personalized.get(nid, 0.0) > 0.0 else 0.0
        return (seeded, score)

    for nid, score in sorted(rank.items(), key=_rank_sort_key, reverse=True)[:top]:
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

    # G13: surface why personalisation didn't engage when caller passed
    # a query — silent fallback to global rank is the audit's complaint.
    personalization_reason: str | None = None
    if query and query.strip() and not personalized:
        personalization_reason = "no_candidate_labels_matched"
    return _ok(
        {"nodes": results},
        meta={
            "backend": be.backend_id,
            "node_count": N,
            "node_cap": _NODE_CAP,  # G15: was hidden default; expose it
            "iterations": iterations,
            "damping": damping,
            "result_truncated": truncated,
            "personalized": bool(personalized),
            "personalization_reason": personalization_reason,
        },
    )
