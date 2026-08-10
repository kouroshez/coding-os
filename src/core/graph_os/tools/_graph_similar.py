"""Semantic ranking: cos_graph_similar and cos_graph_search.

Private module of graph_os.tools.graph — import via the graph module,
never directly (the kernel imports this file at its bottom).
"""

from __future__ import annotations

import difflib
from typing import Any

from ..backend import BackendUnavailable
from ..types import GraphNode
from . import graph as _kernel
from ._graph_envelope import (
    _fail,
    _ok,
    logger,
)
from ._graph_lookup import (
    _fail_uid_not_found,
    _fts5_safe_query,
    _resolve_uid,
)
from ._graph_walk import NodeSummary


def _similar_from_persisted(
    be: Any,
    root: GraphNode,
    *,
    top_k: int,
    confidence_min: float,
    resolved_from: str,
) -> dict[str, Any] | None:
    """Rank similar nodes from persisted graph_node embeddings (one encode,
    full pool). Returns the _ok envelope when persisted vectors are usable,
    else None so the caller falls back to the on-the-fly difflib path.
    """
    conn = getattr(be, "_conn", None)
    if conn is None:
        return None
    try:
        from thinking_os.embeddings import (
            embed_text,
            is_available,
            persisted_similarity_floor,
            search_similar,
        )
    except ImportError:
        return None
    if not is_available():
        return None
    ref_text = f"{root.label or ''} {root.signature or ''} {root.doc_blob or ''}".strip()
    if not ref_text:
        return None
    # Over-fetch beyond top_k to absorb the root self-hit + any identifier /
    # external rows, then trim.
    overfetch = max(top_k * 4, top_k + 20)
    # ANN fast path: vec0 kNN is sublinear, so this stays fast as the graph
    # grows orders of magnitude. Returns None when the extension is absent →
    # fall through to the brute-force streaming scan (always correct, O(N)).
    hits: list[dict[str, Any]] | None = None
    try:
        from graph_os import vec_index

        ref_blob = embed_text(ref_text)
        ann = vec_index.knn(conn, ref_blob, overfetch) if ref_blob else None
        if ann is not None:
            hits = [{"source_id": sid, "score": cos} for sid, cos in ann]
    except Exception as exc:
        logger.debug("vec ann path skipped (%s); falling back to brute force", exc)
    if hits is None:
        try:
            hits = search_similar(
                conn, ref_text, source_tables=["graph_nodes"], limit=overfetch, threshold=0.0
            )
        except Exception as exc:  # fail-open → caller falls back to difflib
            logger.debug("similar persisted path skipped: %s", exc)
            return None
    if not hits:
        return None
    ids = [h["source_id"] for h in hits]
    placeholders = ",".join("?" * len(ids))
    id_to_uid = {
        row[0]: row[1]
        for row in conn.execute(
            f"SELECT id, uid FROM graph_nodes WHERE id IN ({placeholders})", ids
        ).fetchall()
    }
    score_by_id = {h["source_id"]: h["score"] for h in hits}
    wanted = [id_to_uid[i] for i in ids if i in id_to_uid and id_to_uid[i] != root.uid]
    nodes_by_uid = be.get_nodes_bulk(wanted)
    # Cap the floor at the model-calibrated value (MiniLM ~0.25, BGE-M3 ~0.6)
    # so a legacy confidence_min default can't suppress the persisted path;
    # raw cosine and the legacy blended score live on different scales (P6).
    effective_floor = min(confidence_min, persisted_similarity_floor())
    scored: list[tuple[float, GraphNode]] = []
    for i in ids:  # ids are already score-descending from search_similar
        uid = id_to_uid.get(i)
        if uid is None or uid == root.uid:
            continue
        node = nodes_by_uid.get(uid)
        if node is None or node.kind == "identifier" or uid.startswith("code:external:"):
            continue
        sim = score_by_id.get(i, 0.0)
        if sim >= effective_floor:
            scored.append((sim, node))
    if not scored:
        return None
    total = len(scored)
    top_k_eff = max(1, top_k)
    results = [
        {**NodeSummary.from_node(n).to_dict(), "similarity": round(r, 4)}
        for r, n in scored[:top_k_eff]
    ]
    return _ok(
        {
            "root": NodeSummary.from_node(root).to_dict(),
            "results": results,
            "total_count": total,
        },
        meta={
            "backend": be.backend_id,
            "scorer": "persisted-embeddings",
            "top_k": top_k_eff,
            "floor": round(effective_floor, 3),
            "result_truncated": total > top_k_eff,
            "resolved_from": resolved_from,
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
        be = _kernel._backend(backend=backend)
    except BackendUnavailable as exc:
        return _fail("unavailable", str(exc), retryable=True)
    root, tried_uids, resolved_from = _resolve_uid(be, uid)
    if root is None:
        return _fail_uid_not_found(uid, tried_uids)

    # I.1: fast path — rank from persisted graph_node embeddings (one encode,
    # full pool, ~10ms) instead of encoding ~200 candidates on the fly
    # (~1800ms measured). Returns None when no persisted vectors exist (or
    # embeddings unavailable), falling through to the difflib baseline below.
    fast = _similar_from_persisted(
        be, root, top_k=top_k, confidence_min=confidence_min, resolved_from=resolved_from
    )
    if fast is not None:
        return fast

    # B13: use sample_nodes for a breadth candidate pool. NOTE: sample_nodes
    # draws ORDER BY id ASC LIMIT — a fixed prefix of the kind, not a uniform
    # sample. So a structural near-twin outside that window is never scored
    # (round-5 audit: count_nodes' twin count_edges, same class, was never a
    # candidate). Until the sampler is made representative (follow-up task),
    # we GUARANTEE the root's container-siblings are scored below — they are
    # the most likely near-twins, so this fixes the dominant failure mode.
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

    # Sibling augmentation: pull every node sharing the root's container
    # (class / file / module) via the CONTAINS spine so true structural
    # twins are always in the pool regardless of the sample window. One
    # bulk fetch on the collected sibling uids — not a per-sibling get_node
    # round-trip — keeps this a single query.
    try:
        sibling_uids: list[str] = []
        for parent_edge in be.list_edges(target_uid=root.uid, edge_types=["contains"], limit=8):
            sibling_uids.extend(
                e.target_uid
                for e in be.list_edges(
                    source_uid=parent_edge.source_uid,
                    edge_types=["contains"],
                    limit=1000,
                )
            )
        if sibling_uids:
            raw_candidates.extend(be.get_nodes_bulk(sibling_uids).values())
    except Exception as exc:  # fail-open: augmentation is best-effort
        logger.debug("similar sibling augmentation skipped: %s", exc)

    # F3: same-label cross-file augmentation. sample_nodes draws a fixed
    # id-prefix window and the sibling sweep only covers the root's own
    # container, so structural twins in OTHER files (e.g. the 9 `extract()`
    # functions across extractor modules) were never candidates. Pull
    # same-kind nodes sharing the root's label so cross-file near-twins are
    # always scored. Cheap + deterministic (no RANDOM()).
    _sim_conn = getattr(be, "_conn", None)
    if root.label and _sim_conn is not None:
        try:
            same_label_uids = [
                r[0]
                for r in _sim_conn.execute(
                    "SELECT uid FROM graph_nodes WHERE kind = ? AND label = ? LIMIT 200",
                    (root.kind, root.label),
                ).fetchall()
            ]
            if same_label_uids:
                raw_candidates.extend(be.get_nodes_bulk(same_label_uids).values())
        except Exception as exc:  # fail-open
            logger.debug("similar same-label augmentation skipped: %s", exc)

    # G21: drop external/orphan/unresolved stubs from the candidate pool —
    # they otherwise dominate similarity for any noise-shaped input
    # (`unresolved:str` returned 120 noise neighbours). Dedup by uid since
    # the sample and the sibling sweep can overlap. Seed with `root.uid`
    # (not just the raw `uid`): the sibling sweep walks root's container and
    # always re-includes root itself, and when the input resolved fuzzily
    # (resolved_from != "direct") root.uid != uid — so excluding only the
    # raw input would let the queried node score ~1.0 against itself.
    seen_uids: set[str] = {root.uid}
    candidates: list[GraphNode] = []
    for n in raw_candidates:
        if n.uid == uid or n.uid in seen_uids:
            continue
        if n.uid.startswith("code:external:unresolved:") or n.kind == "identifier":
            continue
        seen_uids.add(n.uid)
        candidates.append(n)

    # Use BGE-M3 embeddings when the model is available;
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
                    for n, vec in zip(candidates, cand_vecs, strict=False):
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
    top_k_eff = max(1, top_k)
    total = len(scored)
    results = [
        {**NodeSummary.from_node(n).to_dict(), "similarity": round(r, 4)}
        for r, n in scored[:top_k_eff]
    ]
    return _ok(
        {
            "root": NodeSummary.from_node(root).to_dict(),
            "results": results,
            "total_count": total,
        },
        meta={
            "backend": be.backend_id,
            "scorer": scorer_name,
            "top_k": top_k_eff,
            "result_truncated": total > top_k_eff,
            "resolved_from": resolved_from,
        },
    )


def cos_graph_search(
    query: str,
    *,
    top_k: int = 10,
    backend: str | None = None,
) -> dict[str, Any]:
    """Hybrid semantic + lexical search over indexed code symbols by free text.

    Blends three signals: semantic cosine (ANN vec0 → cosine, brute-force
    fallback), FTS5 lexical presence, and graph in-degree (centrality). Answers
    "where is the code that does X?" without knowing a symbol name.
    """
    if not query or not query.strip():
        return _fail("validation", "query must be non-empty")
    try:
        be = _kernel._backend(backend=backend)
    except BackendUnavailable as exc:
        return _fail("unavailable", str(exc), retryable=True)
    conn = getattr(be, "_conn", None)
    if conn is None:
        return _fail("unavailable", "backend has no SQLite connection", retryable=True)

    top_k_eff = max(1, min(int(top_k), 50))
    pool = top_k_eff * 5

    # --- semantic signal (ANN → brute fallback) ---
    sem_by_id: dict[int, float] = {}
    try:
        from thinking_os.embeddings import embed_text, is_available, search_similar

        if is_available():
            blob = embed_text(query)
            if blob:
                from graph_os import vec_index

                ann = vec_index.knn(conn, blob, pool)
                if ann is None:
                    hits = search_similar(
                        conn, query, source_tables=["graph_nodes"], limit=pool, threshold=0.0
                    )
                    ann = [(h["source_id"], h["score"]) for h in hits]
                sem_by_id = {int(sid): float(cos) for sid, cos in ann}
    except Exception as exc:
        logger.debug("graph_search semantic signal skipped: %s", exc)

    # --- lexical signal (FTS5 presence over graph_nodes_fts) ---
    lex_ids: set[int] = set()
    fts_q = _fts5_safe_query(query)
    if fts_q:
        try:
            lex_ids = {
                int(r[0])
                for r in conn.execute(
                    "SELECT rowid FROM graph_nodes_fts WHERE graph_nodes_fts MATCH ? LIMIT ?",
                    (fts_q, pool),
                ).fetchall()
            }
        except Exception as exc:
            logger.debug("graph_search lexical signal skipped: %s", exc)

    cand_ids = set(sem_by_id) | lex_ids
    if not cand_ids:
        return _ok(
            {"query": query, "results": [], "total_count": 0},
            meta={"backend": be.backend_id, "scorer": "hybrid", "top_k": top_k_eff},
        )

    # --- centrality signal (in-degree over the candidate set, normalised) ---
    deg_by_id: dict[int, int] = {}
    id_list = list(cand_ids)
    ph = ",".join("?" * len(id_list))
    try:
        for r in conn.execute(
            f"SELECT target_id, COUNT(*) FROM graph_edges_v12 "
            f"WHERE target_id IN ({ph}) GROUP BY target_id",
            id_list,
        ).fetchall():
            deg_by_id[int(r[0])] = int(r[1])
    except Exception as exc:
        logger.debug("graph_search centrality signal skipped: %s", exc)
    max_deg = max(deg_by_id.values(), default=0)

    # --- blend + resolve to nodes ---
    id_to_uid = {
        int(row[0]): row[1]
        for row in conn.execute(
            f"SELECT id, uid FROM graph_nodes WHERE id IN ({ph})", id_list
        ).fetchall()
    }
    nodes_by_uid = be.get_nodes_bulk(list(id_to_uid.values()))
    scored: list[tuple[float, GraphNode]] = []
    for gid in cand_ids:
        uid = id_to_uid.get(gid)
        node = nodes_by_uid.get(uid) if uid else None
        if node is None or node.kind == "identifier" or uid.startswith("code:external:"):
            continue
        sem = sem_by_id.get(gid, 0.0)
        lex = 1.0 if gid in lex_ids else 0.0
        deg = (deg_by_id.get(gid, 0) / max_deg) if max_deg else 0.0
        score = 0.7 * sem + 0.2 * lex + 0.1 * deg
        scored.append((score, node))
    scored.sort(key=lambda p: p[0], reverse=True)
    total = len(scored)
    results = [
        {**NodeSummary.from_node(n).to_dict(), "score": round(s, 4)} for s, n in scored[:top_k_eff]
    ]
    return _ok(
        {"query": query, "results": results, "total_count": total},
        meta={
            "backend": be.backend_id,
            "scorer": "hybrid",
            "top_k": top_k_eff,
            "result_truncated": total > top_k_eff,
        },
    )
