"""The two retrieval passes behind `cos_doc_search`, and their SQL pre-filter.

Semantic ranks by embedding cosine; lexical ranks by FTS5 rank with a LIKE scan
as the last resort when FTS is absent. Both hydrate the same result shape and
both narrow their candidate set through `_build_metadata_filter` first — vector
finds meaning, metadata decides which docs are allowed to compete.
"""

from __future__ import annotations

import logging
import sqlite3
from typing import Any

logger = logging.getLogger("coding_os.tools.docs")

# Default cap on results before dedupe + final limit. Pulling 3x the requested
# limit gives the dedupe step room to work without losing too much recall.
_OVERFETCH_MULTIPLIER = 3


def _resolve_doc_threshold() -> float:
    # M5: an unset threshold resolves to the active model's doc-calibrated
    # cosine floor (MiniLM 0.05 / BGE-M3 0.50) so semantic doc search does not
    # return everything after the BGE-M3 cutover. Falls back to the MiniLM-era
    # value when the embeddings module is unavailable.
    try:
        from embeddings import doc_similarity_floor

        return doc_similarity_floor()
    except ImportError:
        return 0.05


def _build_metadata_filter(
    *,
    source_types: list[str] | None,
    domain: str | None,
    layer: str | None,
    since_iso: str | None,
    include_inactive: bool,
    table_alias: str = "",
) -> tuple[str, list[Any]]:
    p = table_alias if table_alias.endswith(".") or not table_alias else f"{table_alias}."
    if table_alias and not p.endswith("."):
        p = f"{table_alias}."
    parts: list[str] = []
    params: list[Any] = []
    if source_types:
        parts.append(f"{p}source_type IN ({','.join('?' * len(source_types))})")
        params.extend(source_types)
    if domain is not None:
        parts.append(f"{p}domain = ?")
        params.append(domain)
    if layer is not None:
        parts.append(f"{p}layer = ?")
        params.append(layer)
    if since_iso is not None:
        parts.append(f"{p}updated_iso >= ?")
        params.append(since_iso)
    if not include_inactive:
        parts.append(f"({p}is_active = 1 OR {p}is_active IS NULL)")
    if not parts:
        return "", []
    return " AND " + " AND ".join(parts), params


def _semantic_search(
    conn: sqlite3.Connection,
    query: str,
    limit: int,
    threshold: float,
    *,
    source_types: list[str] | None = None,
    domain: str | None = None,
    layer: str | None = None,
    since_iso: str | None = None,
    include_inactive: bool = False,
) -> list[dict]:
    # Empty list is the fallback signal — callers route to lexical search on empty.
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
    md_clause, md_params = _build_metadata_filter(
        source_types=source_types,
        domain=domain,
        layer=layer,
        since_iso=since_iso,
        include_inactive=include_inactive,
    )
    sql += md_clause
    params.extend(md_params)

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
        hydrated.append(
            {
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
            }
        )
    hydrated.sort(key=lambda d: d["score"], reverse=True)
    return hydrated


def _lexical_search(
    conn: sqlite3.Connection,
    query: str,
    limit: int,
    *,
    source_types: list[str] | None = None,
    domain: str | None = None,
    layer: str | None = None,
    since_iso: str | None = None,
    include_inactive: bool = False,
) -> list[dict]:
    # LIKE fallback (FTS absent / pre-v9) is intentionally scan-heavy — last-resort only.
    from database import has_document_chunks_fts  # avoid circular at module top

    overfetch = limit * _OVERFETCH_MULTIPLIER
    md_kwargs = {
        "source_types": source_types,
        "domain": domain,
        "layer": layer,
        "since_iso": since_iso,
        "include_inactive": include_inactive,
    }

    if has_document_chunks_fts(conn):
        try:
            return _fts_hydrate(conn, query, overfetch, **md_kwargs)
        except sqlite3.OperationalError as exc:
            # FTS5 query syntax errors (special chars) — fall through to LIKE.
            logger.debug("_lexical_search FTS failed, falling back to LIKE: %s", exc)

    return _like_hydrate(conn, query, overfetch, **md_kwargs)


def _fts_hydrate(
    conn: sqlite3.Connection,
    query: str,
    limit: int,
    *,
    source_types: list[str] | None = None,
    domain: str | None = None,
    layer: str | None = None,
    since_iso: str | None = None,
    include_inactive: bool = False,
) -> list[dict]:
    md_clause, md_params = _build_metadata_filter(
        source_types=source_types,
        domain=domain,
        layer=layer,
        since_iso=since_iso,
        include_inactive=include_inactive,
        table_alias="dc",
    )
    sql = (
        "SELECT dc.id, dc.source_path, dc.source_type, dc.chunk_index, "
        "dc.heading_path, dc.content, dc.priority, dc.mtime, f.rank AS fts_rank "
        "FROM document_chunks_fts f "
        "JOIN document_chunks dc ON dc.id = f.rowid "
        "WHERE document_chunks_fts MATCH ?" + md_clause + " ORDER BY f.rank LIMIT ?"
    )
    params: list[Any] = [query, *md_params, limit]
    rows = conn.execute(sql, params).fetchall()

    hydrated: list[dict] = []
    for row in rows:
        # Normalize FTS5 rank (negative, closer to 0 = better) into [0, 1].
        raw_rank = abs(row["fts_rank"] or 0.0)
        lexical_score = 1.0 / (1.0 + raw_rank)
        priority = row["priority"] if row["priority"] is not None else 0.5
        final_score = lexical_score * (0.85 + 0.3 * priority)
        hydrated.append(
            {
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
            }
        )
    return hydrated


def _like_hydrate(
    conn: sqlite3.Connection,
    query: str,
    limit: int,
    *,
    source_types: list[str] | None = None,
    domain: str | None = None,
    layer: str | None = None,
    since_iso: str | None = None,
    include_inactive: bool = False,
) -> list[dict]:
    like_pattern = f"%{query}%"
    params: list[Any] = [like_pattern, like_pattern]
    sql = (
        "SELECT id, source_path, source_type, chunk_index, heading_path, "
        "content, priority, mtime FROM document_chunks "
        "WHERE (content LIKE ? OR heading_path LIKE ?)"
    )
    md_clause, md_params = _build_metadata_filter(
        source_types=source_types,
        domain=domain,
        layer=layer,
        since_iso=since_iso,
        include_inactive=include_inactive,
    )
    sql += md_clause
    params.extend(md_params)
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
