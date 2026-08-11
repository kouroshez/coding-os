"""cos_search — the lexical + semantic retrieval pass over agent memory.

One query runs the FTS5 (or LIKE-fallback) scan and the vector recall, fuses
the two orderings, and returns the diversified top-N. Ranking lives in
`_memory_ranking`; vector recall in `_memory_semantic`.
"""

from __future__ import annotations

import logging
import sqlite3

from ._memory_ranking import (
    _compute_score,
    _days_since,
    _fts5_safe_query,
    _mmr_select,
    _re_verify_recommended,
    _rrf_fuse,
)
from ._memory_semantic import _augment_with_semantic

logger = logging.getLogger("thinking_os.memory")

VALID_MEMORY_TYPES = {
    "pattern",
    "workflow",
    "error",
    "decision",
    "discovery",
    "config",
    "working",
    "changelog",
}


def memory_search(
    conn: sqlite3.Connection,
    *,
    query: str,
    limit: int = 5,
    memory_type: str | None = None,
    use_fts5: bool = True,
    min_confidence: float = 0.0,
    since_days: int | None = None,
    include_body: bool = False,
) -> dict:
    """Search observations and learned_patterns with 5-signal ranking.

    Stage-1 RAG metadata pre-filter:
      - `min_confidence` drops learned_patterns whose confidence is below
        the threshold BEFORE ranking. Stale low-confidence patterns can
        otherwise crowd out fresh high-signal hits via raw text overlap.
      - `since_days` caps recency; rows older than now-`since_days` are
        dropped in pre-filter. Observations and patterns both filtered.

    Args:
        conn: SQLite connection.
        query: Search text.
        limit: Max results (1-20, default 5).
        memory_type: Filter by memory type (optional).
        use_fts5: Whether FTS5 is available.
        min_confidence: Drop learned_patterns with confidence below this
            value (0.0-1.0; default 0.0 = no filter). Common: 0.3 to skip
            de-cayed unvalidated patterns.
        since_days: Drop rows older than now-`since_days`. None = no cap.
            Common: 90 (one quarter) for "recent" queries.
        include_body: When True, keep an untruncated `content` body on each
            observation/pattern hit (the Hub search UI opts in; agents omit
            it to stay lean).

    Returns:
        Dict with results list and metadata.
    """
    if not query or not query.strip():
        return {"results": [], "count": 0, "source": "empty_query"}

    limit = max(1, min(20, limit))
    # Mechanical 'changelog' breadcrumbs are hidden from recall unless explicitly
    # requested (audit opt-in). Filtered in SQL so they never consume the LIMIT*3
    # fetch budget and crowd out real hits.
    _hide_changelog = memory_type != "changelog"
    _cl_fts = " AND COALESCE(o.memory_type, '') != 'changelog'" if _hide_changelog else ""
    _cl_like = " AND COALESCE(memory_type, '') != 'changelog'" if _hide_changelog else ""
    like_pattern = f"%{query}%"
    candidates: list[dict] = []
    since_clause = ""
    since_param: list = []
    if since_days is not None and since_days > 0:
        since_clause = " AND created_at >= datetime('now', '-' || ? || ' days')"
        since_param = [int(since_days)]

    # --- Search observations ---
    if use_fts5:
        try:
            obs_rows = conn.execute(
                "SELECT o.id, o.title, o.memory_type, o.impact_score, o.created_at, "
                "o.concepts, o.access_count, o.files_modified, "
                "bm25(observations_fts, 3.0, 1.0, 1.0) AS fts_rank "
                "FROM observations_fts f "
                "JOIN observations o ON o.id = f.rowid "
                "WHERE observations_fts MATCH ?" + _cl_fts + " "
                "ORDER BY fts_rank LIMIT ?",
                (_fts5_safe_query(query), limit * 3),
            ).fetchall()
        except sqlite3.OperationalError:
            # FTS5 table might not exist — fall back
            obs_rows = []
            use_fts5 = False
    if not use_fts5:
        obs_rows = conn.execute(
            "SELECT id, title, memory_type, impact_score, created_at, concepts, "
            "access_count, files_modified, 0.5 AS fts_rank "
            "FROM observations "
            "WHERE (title LIKE ? OR narrative LIKE ? OR concepts LIKE ?)"
            + _cl_like
            + since_clause
            + " ORDER BY created_at DESC LIMIT ?",
            (like_pattern, like_pattern, like_pattern, *since_param, limit * 3),
        ).fetchall()
    elif since_param:
        # FTS5 path doesn't honor since_clause natively — apply post-filter
        obs_rows = [r for r in obs_rows if _days_since(dict(r).get("created_at")) <= since_days]

    for row in obs_rows:
        row_dict = dict(row)
        if memory_type and row_dict.get("memory_type") != memory_type:
            continue
        # FTS5 bm25 is negative; a stronger match is more negative (larger abs).
        # Map to a [0,1) relevance that increases with match strength so the
        # title-weighted column boost actually lifts title hits above body hits.
        raw_rank = abs(row_dict.get("fts_rank", 0) or 0)
        relevance = (1.0 - 1.0 / (1.0 + raw_rank)) if use_fts5 else 0.5
        days = _days_since(row_dict.get("created_at"))
        score = _compute_score(
            relevance=relevance,
            confidence=0.5,  # observations don't have confidence
            recency_days=days,
            impact=row_dict.get("impact_score", 0.5) or 0.5,
            access_count=row_dict.get("access_count", 0) or 0,
        )
        candidates.append(
            {
                "id": row_dict["id"],
                "title": (row_dict.get("title") or "")[:60],
                **({"content": row_dict.get("title") or ""} if include_body else {}),
                "confidence": 0.5,
                "impact_score": row_dict.get("impact_score", 0.5),
                "memory_type": row_dict.get("memory_type", "discovery"),
                "source_table": "observations",
                "concepts": row_dict.get("concepts"),
                "score": score,
                "semantic_score": 0.0,
                "re_verify_recommended": _re_verify_recommended(
                    row_dict.get("files_modified"), row_dict.get("created_at")
                ),
            }
        )

    # --- Search learned_patterns ---
    if use_fts5:
        # No FTS5 on learned_patterns — use LIKE
        pass
    lp_rows = conn.execute(
        "SELECT id, pattern, memory_type, confidence, impact_score, "
        "access_count, created_at, concepts, domain "
        "FROM learned_patterns "
        "WHERE (pattern LIKE ? OR concepts LIKE ?) "
        "AND confidence >= ?" + since_clause + " ORDER BY confidence DESC LIMIT ?",
        (like_pattern, like_pattern, float(min_confidence), *since_param, limit * 3),
    ).fetchall()

    for row in lp_rows:
        row_dict = dict(row)
        if memory_type and row_dict.get("memory_type") != memory_type:
            continue
        days = _days_since(row_dict.get("created_at"))
        score = _compute_score(
            relevance=0.6,  # LIKE match = moderate relevance
            confidence=row_dict.get("confidence", 0.5) or 0.5,
            recency_days=days,
            impact=row_dict.get("impact_score", 0.5) or 0.5,
            access_count=row_dict.get("access_count", 0) or 0,
        )
        candidates.append(
            {
                "id": row_dict["id"],
                "title": (row_dict.get("pattern") or "")[:60],
                **({"content": row_dict.get("pattern") or ""} if include_body else {}),
                "confidence": row_dict.get("confidence", 0.5),
                "impact_score": row_dict.get("impact_score", 0.5),
                "memory_type": row_dict.get("memory_type", "pattern"),
                "source_table": "learned_patterns",
                "concepts": row_dict.get("concepts"),
                "score": score,
                "semantic_score": 0.0,
            }
        )

    # --- semantic augmentation via embeddings ---
    semantic_used = _augment_with_semantic(
        conn=conn,
        query=query,
        candidates=candidates,
        memory_type=memory_type,
        overfetch=limit * 3,
        min_confidence=min_confidence,
        since_days=since_days,
    )

    # --- RRF-fuse lexical+semantic rankings, hard-dedup titles, MMR-diversify ---
    _rrf_fuse(candidates)
    candidates.sort(key=lambda x: x["score"], reverse=True)

    # Exact-title hard dedup: identical titles (duplicate discovery rows, or the
    # same mechanical breadcrumb recurring across sessions) can otherwise crowd
    # out distinct hits. Candidates are score-sorted, so the first occurrence wins.
    deduped: list[dict] = []
    seen_titles: set[str] = set()
    for c in candidates:
        title_key = (c.get("title") or "").strip().lower()
        if title_key and title_key in seen_titles:
            continue
        if title_key:
            seen_titles.add(title_key)
        deduped.append(c)

    # MMR then drops near-duplicate (non-identical) content from the slice.
    results = _mmr_select(deduped, limit)

    # --- Graph expansion: find related nodes from concept_graph ---
    if results and len(results) < limit:
        try:
            from graph import query_related as _graph_query

            # Extract file paths and concepts from top results
            seed_nodes: set[str] = set()
            for r in results[:3]:
                title = r.get("title", "")
                if "/" in title:
                    # Likely a file path in title like "Modified backend/..."
                    parts = title.replace("Modified ", "").replace("Created ", "").strip()
                    seed_nodes.add(parts.lower())

            for node in list(seed_nodes)[:2]:
                graph_results = _graph_query(conn, node=node, max_hops=1, limit=3)
                for gn in graph_results.get("nodes", []):
                    results.append(
                        {
                            "id": None,
                            "title": f"[Related] {gn['node']}",
                            "confidence": 0.3,
                            "impact_score": 0.3,
                            "memory_type": "graph_expansion",
                            "source_table": "concept_graph",
                        }
                    )
                    if len(results) >= limit:
                        break
        except Exception:
            pass  # graph may not exist (pre-v4)

    # Drift contract: every result carries the flag (accurate for observations;
    # patterns/graph/semantic-only hits default False — they have no file ref).
    for r in results:
        r.setdefault("re_verify_recommended", False)

    # Read-only contract: raw search does NOT bump access_count or confidence —
    # reinforcement happens only on the cos_details drill-in. Bumping confidence
    # here inflated every matched pattern +0.02 per call, polluting both the
    # min_confidence gate and the confidence-weighted ranking.

    # --- Remove internal-only fields from output ---
    for r in results:
        r.pop("score", None)
        r.pop("concepts", None)

    source_label = "fts5" if use_fts5 else "like"
    if semantic_used:
        source_label = f"{source_label}+semantic"

    return {
        "results": results,
        "count": len(results),
        "source": source_label,
    }
