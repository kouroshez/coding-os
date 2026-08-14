"""Centrality scoring plus the noise vocabulary and batched edge scan it shares.

Private module of graph_os.tools.graph — import via the graph module,
never directly (the kernel imports this file at its bottom).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from ..backend import BackendUnavailable
from . import graph as _kernel
from ._graph_envelope import (
    _clamp_int,
    _fail,
    _ok,
    _validate_enum,
    _validate_positive_int,
    logger,
)
from ._graph_walk import _BEHAVIOURAL_EDGE_TYPES

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
            # validate against the canonical NodeKind enum, not the
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
            # containment skeleton the degree pass excludes.
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
