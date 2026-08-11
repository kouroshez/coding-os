"""Semantic augmentation for memory search.

Vector recall runs alongside the lexical scan and contributes candidates the
keyword query never had the words for; each hit is hydrated back into the same
row shape so both orderings can be fused downstream.
"""

from __future__ import annotations

import logging
import sqlite3

from ._memory_ranking import _compute_score, _days_since

logger = logging.getLogger("thinking_os.memory")


def _augment_with_semantic(
    *,
    conn: sqlite3.Connection,
    query: str,
    candidates: list[dict],
    memory_type: str | None,
    overfetch: int,
    min_confidence: float = 0.0,
    since_days: int | None = None,
) -> bool:
    # Merges embedding hits into `candidates` (mutates it): sets semantic_score on
    # rows already present, appends semantic-only hits. Returns False (graceful
    # fallback) when embeddings are unavailable.
    try:
        from embeddings import is_available, memory_similarity_floor, search_similar
    except ImportError as exc:
        logger.debug("Semantic augmentation unavailable (module missing): %s", exc)
        return False

    if not is_available():
        return False

    try:
        semantic_hits = search_similar(
            conn,
            query=query,
            source_tables=["observations", "learned_patterns"],
            limit=overfetch,
            threshold=memory_similarity_floor(),
        )
    except sqlite3.OperationalError as exc:
        logger.debug("Semantic augmentation skipped (table missing): %s", exc)
        return False
    except Exception as exc:  # pragma: no cover - defensive against model errors
        logger.debug("Semantic augmentation skipped (unexpected): %s", exc)
        return False

    if not semantic_hits:
        return False

    # Index existing candidates for O(1) merge by (table, id)
    by_key: dict[tuple[str, int], dict] = {(c["source_table"], c["id"]): c for c in candidates}

    for hit in semantic_hits:
        key = (hit["source_table"], hit["source_id"])
        if key in by_key:
            by_key[key]["semantic_score"] = hit["score"]
            continue

        # Semantic-only hit — hydrate the row and append as a new candidate.
        new_candidate = _hydrate_row_for_semantic_hit(
            conn,
            hit["source_table"],
            hit["source_id"],
            min_confidence=min_confidence,
            since_days=since_days,
        )
        if new_candidate is None:
            continue
        mt = new_candidate.get("memory_type")
        if memory_type:
            if mt != memory_type:
                continue
        elif mt == "changelog":
            continue
        new_candidate["semantic_score"] = hit["score"]
        candidates.append(new_candidate)
        by_key[key] = new_candidate

    return True


def _hydrate_row_for_semantic_hit(
    conn: sqlite3.Connection,
    source_table: str,
    source_id: int,
    *,
    min_confidence: float = 0.0,
    since_days: int | None = None,
) -> dict | None:
    # Shape a semantic-only hit like the FTS5/LIKE candidate dicts; None if the
    # row is gone OR fails the Stage-1 filters. The lexical channels apply
    # min_confidence/since_days in SQL; the semantic channel must honor them too
    # or a decayed/old pattern re-enters recall through the embedding path.
    _capped = since_days is not None and since_days > 0
    if source_table == "observations":
        row = conn.execute(
            "SELECT id, title, memory_type, impact_score, created_at "
            "FROM observations WHERE id = ?",
            (source_id,),
        ).fetchone()
        if row is None:
            return None
        days = _days_since(row["created_at"])
        if _capped and days > since_days:
            return None
        return {
            "id": row["id"],
            "title": (row["title"] or "")[:60],
            "confidence": 0.5,
            "impact_score": row["impact_score"] or 0.5,
            "memory_type": row["memory_type"] or "discovery",
            "source_table": "observations",
            # Baseline 5-signal for semantic-only hit: low relevance, default conf
            "score": _compute_score(
                relevance=0.3,
                confidence=0.5,
                recency_days=days,
                impact=row["impact_score"] or 0.5,
                access_count=0,
            ),
            "semantic_score": 0.0,
        }

    if source_table == "learned_patterns":
        row = conn.execute(
            "SELECT id, pattern, memory_type, confidence, impact_score, "
            "access_count, created_at FROM learned_patterns WHERE id = ?",
            (source_id,),
        ).fetchone()
        if row is None:
            return None
        if (row["confidence"] or 0.5) < min_confidence:
            return None
        days = _days_since(row["created_at"])
        if _capped and days > since_days:
            return None
        return {
            "id": row["id"],
            "title": (row["pattern"] or "")[:60],
            "confidence": row["confidence"] or 0.5,
            "impact_score": row["impact_score"] or 0.5,
            "memory_type": row["memory_type"] or "pattern",
            "source_table": "learned_patterns",
            "score": _compute_score(
                relevance=0.3,
                confidence=row["confidence"] or 0.5,
                recency_days=days,
                impact=row["impact_score"] or 0.5,
                access_count=row["access_count"] or 0,
            ),
            "semantic_score": 0.0,
        }

    return None
