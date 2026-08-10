"""Structure insights: cos_graph_entrypoints, cos_graph_communities, cos_graph_cycles.

Private module of graph_os.tools.graph — import via the graph module,
never directly (the kernel imports this file at its bottom).
"""

from __future__ import annotations

from typing import Any

from ..backend import BackendUnavailable
from . import graph as _kernel
from ._graph_envelope import (
    _clamp_int,
    _fail,
    _ok,
    _validate_enum,
    _validate_positive_int,
)


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
