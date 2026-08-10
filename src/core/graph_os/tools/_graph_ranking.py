"""Personalised PageRank: cos_graph_ranking.

Private module of graph_os.tools.graph — import via the graph module,
never directly (the kernel imports this file at its bottom).
"""

from __future__ import annotations

import re
from typing import Any

from ..backend import BackendUnavailable
from . import graph as _kernel
from ._graph_centrality import (
    _NOISE_MODULE_NAMES,
    _edges_among,
)
from ._graph_envelope import (
    _clamp_int,
    _fail,
    _ok,
    _validate_positive_int,
    logger,
)

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
