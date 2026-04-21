"""
Coding OS — Document RAG search tool (Phase B.4).

Provides `doc_search` — semantic search over the `document_chunks` table
populated by `doc_indexer`. Returns chunk-level results (300-500 tokens each)
with heading_path metadata so the agent can fetch only the relevant slice
of a doc instead of full-reading it.

Public API:
    doc_search(conn, query, source_types, limit, threshold, dedupe_per_source)
        -> list[dict]
"""

from __future__ import annotations

import logging
import re
import sqlite3
from typing import Any, Literal

logger = logging.getLogger("coding_os.tools.docs")

# Default cap on results before dedupe + final limit. Pulling 3x the requested
# limit gives the dedupe step room to work without losing too much recall.
_OVERFETCH_MULTIPLIER = 3

# Default per-source dedupe cap when dedupe_per_source=True. Two chunks per
# source file is the sweet spot — enough for a section + neighbor without
# crowding the result list.
_MAX_PER_SOURCE = 2

# G.7.3 — identifier-looking query detection. Heuristic is deliberately
# permissive: if the user typed something code-shaped we route to FTS first
# because cosine similarity is weak on short literal tokens.
_IDENTIFIER_RE = re.compile(
    r"("
    r"[A-Za-z_][A-Za-z0-9_]*\(\)"     # function call syntax
    r"|[a-z]+(?:_[a-z0-9]+)+"          # snake_case (2+ segments)
    r"|[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]+)+"  # CamelCase (2+ segments)
    r"|TASK-\d+"                       # task id
    r"|`[^`]+`"                        # explicit backtick identifier
    r"|[a-zA-Z_][a-zA-Z0-9_]*\.py|\.ts|\.tsx|\.md"  # file with known ext
    r")"
)


def looks_like_identifier(query: str) -> bool:
    """Return True when `query` contains a code-shaped token.

    PURPOSE:      Pick a retrieval mode in `auto` without round-tripping
                  through embeddings first.
    INPUT:        raw user query string.
    OUTPUT:       bool.
    DEPENDENCIES: none.
    NOTES:        Intentionally false-positive-biased — if unsure, FTS wins
                  on identifier recall and is dirt-cheap. Worst case: FTS
                  returns empty and we fall back to semantic anyway.
    """
    if not query or not query.strip():
        return False
    return bool(_IDENTIFIER_RE.search(query))


SearchMode = Literal["auto", "semantic", "lexical"]


def doc_search(
    conn: sqlite3.Connection,
    query: str,
    source_types: list[str] | None = None,
    limit: int = 5,
    threshold: float = 0.05,
    dedupe_per_source: bool = True,
    mode: SearchMode = "auto",
) -> list[dict]:
    """Semantic + lexical search over project documentation chunks.

    Args:
        conn: Open SQLite connection (must include migration v5+; v9 adds
            the document_chunks_fts table used by the lexical path).
        query: Natural language query (e.g. "commission rate calculation").
        source_types: Optional filter — only return chunks whose source_type
            matches one of these values (e.g. ["prd", "architecture"]).
        limit: Maximum results to return (1-50).
        threshold: Minimum cosine similarity (default 0.05 — tuned for
            all-MiniLM-L6-v2 on short queries).
        dedupe_per_source: When True, return at most _MAX_PER_SOURCE chunks
            per source_path so a single dominant file doesn't crowd out others.
        mode: Retrieval mode (Phase G.7.3):
            - "auto"     → identifier-looking query → FTS first, else semantic;
                           fall back to the other on empty.
            - "semantic" → embeddings-only (legacy behavior).
            - "lexical"  → FTS5 match only (no embedding even if available).

    Returns:
        List of result dicts. Each carries a `retrieval_source` field so
        callers / audit can tell whether the row came from semantic or
        lexical. Empty when nothing matches and no fallback succeeds.
    """
    if not query or not query.strip():
        return []

    # Cap inputs to defensive limits
    limit = max(1, min(int(limit), 50))

    results: list[dict] = []

    if mode == "lexical":
        results = _lexical_search(conn, query, source_types, limit)
    elif mode == "semantic":
        results = _semantic_search(conn, query, source_types, limit, threshold)
    else:  # auto
        # Identifier-looking → FTS first; else semantic first.
        identifier_first = looks_like_identifier(query)
        primary = _lexical_search if identifier_first else _semantic_search
        secondary = _semantic_search if identifier_first else _lexical_search

        results = primary(conn, query, source_types, limit, threshold) \
            if primary is _semantic_search \
            else primary(conn, query, source_types, limit)
        if not results:
            results = secondary(conn, query, source_types, limit, threshold) \
                if secondary is _semantic_search \
                else secondary(conn, query, source_types, limit)

    if dedupe_per_source:
        per_source_count: dict[str, int] = {}
        deduped: list[dict] = []
        for item in results:
            count = per_source_count.get(item["source_path"], 0)
            if count >= _MAX_PER_SOURCE:
                continue
            per_source_count[item["source_path"]] = count + 1
            deduped.append(item)
        results = deduped

    return results[:limit]


def _semantic_search(
    conn: sqlite3.Connection,
    query: str,
    source_types: list[str] | None,
    limit: int,
    threshold: float,
) -> list[dict]:
    """Embedding-based similarity search (previous default path).

    Returns an empty list when embeddings are unavailable or nothing crosses
    the threshold — callers route to lexical fallback on empty.
    """
    try:
        from embeddings import is_available, search_similar
    except ImportError as exc:
        logger.debug("_semantic_search unavailable (module): %s", exc)
        return []

    if not is_available():
        return []

    overfetch = limit * _OVERFETCH_MULTIPLIER
    raw_results = search_similar(
        conn,
        query=query,
        source_tables=["document_chunks"],
        limit=overfetch,
        threshold=threshold,
    )
    if not raw_results:
        return []

    chunk_ids = [r["source_id"] for r in raw_results]
    score_by_id = {r["source_id"]: r["score"] for r in raw_results}

    placeholders = ",".join("?" * len(chunk_ids))
    sql = (
        "SELECT id, source_path, source_type, chunk_index, heading_path, "
        "content, priority, mtime FROM document_chunks "
        f"WHERE id IN ({placeholders})"
    )
    params: list[Any] = list(chunk_ids)
    if source_types:
        type_placeholders = ",".join("?" * len(source_types))
        sql += f" AND source_type IN ({type_placeholders})"
        params.extend(source_types)

    try:
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.OperationalError as exc:
        logger.debug("_semantic_search query failed: %s", exc)
        return []

    hydrated: list[dict] = []
    for row in rows:
        chunk_id = row["id"]
        cosine_score = score_by_id.get(chunk_id, 0.0)
        priority = row["priority"] if row["priority"] is not None else 0.5
        final_score = cosine_score * (0.85 + 0.3 * priority)
        hydrated.append({
            "id": chunk_id,
            "source_path": row["source_path"],
            "source_type": row["source_type"],
            "heading_path": row["heading_path"],
            "content": row["content"],
            "score": final_score,
            "cosine": cosine_score,
            "priority": priority,
            "mtime": row["mtime"],
            "chunk_index": row["chunk_index"],
            "retrieval_source": "semantic",
        })
    hydrated.sort(key=lambda d: d["score"], reverse=True)
    return hydrated


def _lexical_search(
    conn: sqlite3.Connection,
    query: str,
    source_types: list[str] | None,
    limit: int,
) -> list[dict]:
    """FTS5 lexical search over document_chunks_fts (v9+).

    Falls back to a LIKE query when the FTS virtual table is absent
    (FTS5 unavailable or pre-v9). The LIKE path is intentionally scan-heavy
    — acceptable because it is only a last-resort fallback.
    """
    from db import has_document_chunks_fts  # avoid circular at module top

    overfetch = limit * _OVERFETCH_MULTIPLIER

    if has_document_chunks_fts(conn):
        try:
            return _fts_hydrate(conn, query, source_types, overfetch)
        except sqlite3.OperationalError as exc:
            # FTS5 query syntax errors (special chars) — fall through to LIKE.
            logger.debug("_lexical_search FTS failed, falling back to LIKE: %s", exc)

    return _like_hydrate(conn, query, source_types, overfetch)


def _fts_hydrate(
    conn: sqlite3.Connection,
    query: str,
    source_types: list[str] | None,
    limit: int,
) -> list[dict]:
    """FTS5 MATCH join back to document_chunks with priority boost."""
    params: list[Any] = [query, limit]
    sql = (
        "SELECT dc.id, dc.source_path, dc.source_type, dc.chunk_index, "
        "dc.heading_path, dc.content, dc.priority, dc.mtime, f.rank AS fts_rank "
        "FROM document_chunks_fts f "
        "JOIN document_chunks dc ON dc.id = f.rowid "
        "WHERE document_chunks_fts MATCH ? "
        "ORDER BY f.rank LIMIT ?"
    )
    rows = conn.execute(sql, params).fetchall()

    hydrated: list[dict] = []
    for row in rows:
        if source_types and row["source_type"] not in source_types:
            continue
        # Normalize FTS5 rank (negative, closer to 0 = better) into [0, 1].
        raw_rank = abs(row["fts_rank"] or 0.0)
        lexical_score = 1.0 / (1.0 + raw_rank)
        priority = row["priority"] if row["priority"] is not None else 0.5
        final_score = lexical_score * (0.85 + 0.3 * priority)
        hydrated.append({
            "id": row["id"],
            "source_path": row["source_path"],
            "source_type": row["source_type"],
            "heading_path": row["heading_path"],
            "content": row["content"],
            "score": final_score,
            "cosine": 0.0,  # N/A on lexical path
            "priority": priority,
            "mtime": row["mtime"],
            "chunk_index": row["chunk_index"],
            "retrieval_source": "lexical",
        })
    return hydrated


def _like_hydrate(
    conn: sqlite3.Connection,
    query: str,
    source_types: list[str] | None,
    limit: int,
) -> list[dict]:
    """Final fallback: LIKE scan when neither embeddings nor FTS5 available."""
    like_pattern = f"%{query}%"
    params: list[Any] = [like_pattern, like_pattern]
    sql = (
        "SELECT id, source_path, source_type, chunk_index, heading_path, "
        "content, priority, mtime FROM document_chunks "
        "WHERE content LIKE ? OR heading_path LIKE ?"
    )
    if source_types:
        placeholders = ",".join("?" * len(source_types))
        sql += f" AND source_type IN ({placeholders})"
        params.extend(source_types)
    sql += " ORDER BY priority DESC, mtime DESC LIMIT ?"
    params.append(limit)

    try:
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.OperationalError as exc:
        logger.debug("_like_hydrate failed: %s", exc)
        return []

    return [
        {
            "id": r["id"],
            "source_path": r["source_path"],
            "source_type": r["source_type"],
            "heading_path": r["heading_path"],
            "content": r["content"],
            "score": 0.4,  # fixed moderate score for LIKE hits
            "cosine": 0.0,
            "priority": r["priority"] if r["priority"] is not None else 0.5,
            "mtime": r["mtime"],
            "chunk_index": r["chunk_index"],
            "retrieval_source": "lexical-like",
        }
        for r in rows
    ]
