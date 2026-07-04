"""
Thinking OS — MCP memory tools (TASK-142).

4 tools for tiered memory access:
  - thinking_os_search:   index-level results (~50 tokens)
  - thinking_os_timeline: recent activity (~150 tokens)
  - thinking_os_details:  full record (~500 tokens)
  - thinking_os_promote:  pattern → rule/feedback file
"""

from __future__ import annotations

import logging
import re
import sqlite3
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("thinking_os.memory")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
VALID_MEMORY_TYPES = {"pattern", "workflow", "error", "decision", "discovery", "config", "working"}
VALID_SOURCES = {"observations", "learned_patterns", "task_outcomes"}
VALID_PROMOTE_TARGETS = {"feedback", "rule"}

# 5-signal weights
W_RELEVANCE = 0.30
W_CONFIDENCE = 0.25
W_RECENCY = 0.15
W_IMPACT = 0.15
W_ACCESS = 0.15

# Reciprocal Rank Fusion constant (standard k) + MMR diversity trade-off.
RRF_K = 60
MMR_LAMBDA = 0.7


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _days_since(dt_str: str | None) -> float:
    if not dt_str:
        return 999.0
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - dt
        return max(0.0, delta.total_seconds() / 86400.0)
    except (ValueError, TypeError):
        return 999.0


def _recency_score(days: float) -> float:
    # half-life decay: 1.0 at 0 days, 0.5 at 30 days
    return 1.0 / (1.0 + days / 30.0)


def _access_score(count: int) -> float:
    return min(1.0, (count or 0) / 10.0)


def _re_verify_recommended(files_modified: str | None, created_at: str | None) -> bool:
    # Drift signal: True when the referenced file changed after the record was
    # written — the memory may describe code that has since changed, so re-Read
    # before trusting it. See docs/engineering/learning-extraction.md.
    if not files_modified or not created_at:
        return False
    from pathlib import Path

    try:
        path = Path(files_modified.split(",")[0].strip())
        if not path.exists():
            return True  # file gone/renamed → the memory is certainly stale
        created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        return mtime > created
    except (ValueError, OSError, TypeError):
        return False


def _compute_score(
    relevance: float,
    confidence: float,
    recency_days: float,
    impact: float,
    access_count: int,
) -> float:
    return (
        W_RELEVANCE * relevance
        + W_CONFIDENCE * min(1.0, max(0.0, confidence))
        + W_RECENCY * _recency_score(recency_days)
        + W_IMPACT * min(1.0, max(0.0, impact))
        + W_ACCESS * _access_score(access_count)
    )


def _boost_access(conn: sqlite3.Connection, table: str, row_id: int) -> None:
    if table == "learned_patterns":
        conn.execute(
            "UPDATE learned_patterns SET "
            "access_count = access_count + 1, "
            "last_accessed_at = CURRENT_TIMESTAMP, "
            "confidence = MIN(0.95, confidence + 0.02) "
            "WHERE id = ?",
            (row_id,),
        )
    elif table == "observations":
        # observations have no confidence column (impact_score is the belief
        # proxy), but since migration v30 they carry access_count +
        # last_accessed_at so the access/recency-on-use ranking applies.
        conn.execute(
            "UPDATE observations SET "
            "access_count = COALESCE(access_count, 0) + 1, "
            "last_accessed_at = CURRENT_TIMESTAMP "
            "WHERE id = ?",
            (row_id,),
        )


# ---------------------------------------------------------------------------
# semantic augmentation helpers
# ---------------------------------------------------------------------------


def _augment_with_semantic(
    *,
    conn: sqlite3.Connection,
    query: str,
    candidates: list[dict],
    memory_type: str | None,
    overfetch: int,
) -> bool:
    # Merges embedding hits into `candidates` (mutates it): sets semantic_score on
    # rows already present, appends semantic-only hits. Returns False (graceful
    # fallback) when embeddings are unavailable.
    try:
        from embeddings import is_available, search_similar
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
            threshold=0.05,
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
        new_candidate = _hydrate_row_for_semantic_hit(conn, hit["source_table"], hit["source_id"])
        if new_candidate is None:
            continue
        if memory_type and new_candidate.get("memory_type") != memory_type:
            continue
        new_candidate["semantic_score"] = hit["score"]
        candidates.append(new_candidate)
        by_key[key] = new_candidate

    return True


def _hydrate_row_for_semantic_hit(
    conn: sqlite3.Connection,
    source_table: str,
    source_id: int,
) -> dict | None:
    # Shape a semantic-only hit like the FTS5/LIKE candidate dicts; None if the row is gone.
    if source_table == "observations":
        row = conn.execute(
            "SELECT id, title, memory_type, impact_score, created_at "
            "FROM observations WHERE id = ?",
            (source_id,),
        ).fetchone()
        if row is None:
            return None
        days = _days_since(row["created_at"])
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
        days = _days_since(row["created_at"])
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


# ---------------------------------------------------------------------------
# rank fusion + diversity helpers
# ---------------------------------------------------------------------------


def _tokenize(text: str | None) -> set[str]:
    return {t for t in re.split(r"\W+", (text or "").lower()) if t}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    union = len(a | b)
    return len(a & b) / union if union else 0.0


def _rrf_fuse(candidates: list[dict], k: int = RRF_K) -> None:
    # Reciprocal Rank Fusion of the lexical/quality ordering (by 5-signal score)
    # and the semantic ordering (by embedding score), keyed on (source_table,
    # id) so a row present in both lists fuses once instead of duplicating. Each
    # candidate's score is replaced with the fused rank-reciprocal value.
    if not candidates:
        return

    def _key(c: dict) -> tuple:
        return (c["source_table"], c["id"])

    lexical = sorted(candidates, key=lambda c: c.get("score", 0.0), reverse=True)
    lex_rank = {_key(c): i for i, c in enumerate(lexical)}
    semantic = sorted(
        (c for c in candidates if c.get("semantic_score", 0.0) > 0.0),
        key=lambda c: c["semantic_score"],
        reverse=True,
    )
    sem_rank = {_key(c): i for i, c in enumerate(semantic)}
    for c in candidates:
        key = _key(c)
        fused = 1.0 / (k + lex_rank[key] + 1)
        if key in sem_rank:
            fused += 1.0 / (k + sem_rank[key] + 1)
        c["score"] = fused


def _mmr_select(candidates: list[dict], limit: int, lam: float = MMR_LAMBDA) -> list[dict]:
    # Maximal Marginal Relevance: greedily pick the candidate maximizing
    # lam*relevance - (1-lam)*max token-Jaccard similarity to the already-picked
    # set, so near-duplicate memories don't crowd the slice. Relevance is the
    # RRF-fused score MIN-MAX normalized to [0,1] so it stays commensurate with
    # the [0,1] Jaccard penalty — raw RRF reciprocal-rank values (~0.01-0.03)
    # would otherwise be swamped by the diversity term. Sim is over title+concepts.
    pool = list(candidates)
    sig = {id(c): _tokenize(f"{c.get('title') or ''} {c.get('concepts') or ''}") for c in pool}
    scores = [c.get("score", 0.0) for c in pool]
    lo, hi = (min(scores), max(scores)) if scores else (0.0, 0.0)
    span = hi - lo
    rel = {id(c): ((c.get("score", 0.0) - lo) / span if span > 0 else 1.0) for c in pool}
    selected: list[dict] = []
    while pool and len(selected) < limit:
        best = max(
            pool,
            key=lambda c: lam * rel[id(c)]
            - (1.0 - lam) * max((_jaccard(sig[id(c)], sig[id(s)]) for s in selected), default=0.0),
        )
        selected.append(best)
        pool = [c for c in pool if c is not best]
    return selected


# ---------------------------------------------------------------------------
# thinking_os_search
# ---------------------------------------------------------------------------


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
                "WHERE observations_fts MATCH ? "
                "ORDER BY fts_rank LIMIT ?",
                (query, limit * 3),
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
                "content": row_dict.get("title") or "",
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
                "content": row_dict.get("pattern") or "",
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
    )

    # --- RRF-fuse lexical+semantic rankings, hard-dedup titles, MMR-diversify ---
    _rrf_fuse(candidates)
    candidates.sort(key=lambda x: x["score"], reverse=True)

    # Exact-title hard dedup first: auto-capture rows ("Modified <path>") recur
    # once per edit, so an identical title can otherwise crowd out distinct hits.
    # Candidates are score-sorted, so the first occurrence is the best.
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

    # --- Boost access on returned results ---
    for r in results:
        if r.get("source_table") not in ("concept_graph",):
            _boost_access(conn, r["source_table"], r["id"])
    conn.commit()

    # --- Remove internal-only fields from output ---
    for r in results:
        r.pop("score", None)
        r.pop("concepts", None)
        if not include_body:
            r.pop("content", None)

    source_label = "fts5" if use_fts5 else "like"
    if semantic_used:
        source_label = f"{source_label}+semantic"

    return {
        "results": results,
        "count": len(results),
        "source": source_label,
    }


# ---------------------------------------------------------------------------
# thinking_os_timeline
# ---------------------------------------------------------------------------


def memory_timeline(
    conn: sqlite3.Connection,
    *,
    days: int = 30,
    domain: str | None = None,
    limit: int = 20,
) -> dict:
    """Return recent task outcomes and observations.

    Args:
        conn: SQLite connection.
        days: Lookback window (1-365, default 30).
        domain: Filter by domain (optional).
        limit: Max entries (1-50, default 20).

    Returns:
        Dict with timeline entries.
    """
    days = max(1, min(365, days))
    limit = max(1, min(50, limit))
    entries: list[dict] = []

    # Task outcomes
    conditions = ["created_at >= date('now', '-' || ? || ' days')"]
    params: list = [days]
    if domain:
        conditions.append("domain = ?")
        params.append(domain)
    where = " AND ".join(conditions)

    outcome_rows = conn.execute(
        f"SELECT task_id, type, domain, outcome, created_at "
        f"FROM task_outcomes WHERE {where} "
        "ORDER BY created_at DESC LIMIT ?",
        params + [limit],
    ).fetchall()

    for row in outcome_rows:
        r = dict(row)
        entries.append(
            {
                "id": r["task_id"],
                "title": f"{r['task_id']}: {r['type']} ({r['outcome']})",
                "date": r["created_at"],
                "outcome": r["outcome"],
                "type": "task_outcome",
            }
        )

    # Observations
    obs_conditions = ["created_at >= date('now', '-' || ? || ' days')"]
    obs_params: list = [days]
    if domain:
        obs_conditions.append("(concepts LIKE ? OR title LIKE ?)")
        obs_params.extend([f"%{domain}%", f"%{domain}%"])
    obs_where = " AND ".join(obs_conditions)

    obs_rows = conn.execute(
        f"SELECT id, title, memory_type, created_at "
        f"FROM observations WHERE {obs_where} "
        "ORDER BY created_at DESC LIMIT ?",
        obs_params + [limit],
    ).fetchall()

    for row in obs_rows:
        r = dict(row)
        entries.append(
            {
                "id": r["id"],
                "title": (r.get("title") or "")[:40],
                "date": r["created_at"],
                "outcome": None,
                "type": r.get("memory_type", "observation"),
            }
        )

    # Sort combined by date desc, truncate
    entries.sort(key=lambda x: x.get("date") or "", reverse=True)
    return {"entries": entries[:limit], "count": min(len(entries), limit), "days": days}


# ---------------------------------------------------------------------------
# thinking_os_details
# ---------------------------------------------------------------------------


def memory_details(
    conn: sqlite3.Connection,
    *,
    pattern_id: int | str,
    source: str,
) -> dict:
    """Return full record for a pattern, observation, or task outcome.

    Args:
        conn: SQLite connection.
        pattern_id: Row ID (int) or task_id string for task_outcomes.
        source: Table name — one of: observations, learned_patterns, task_outcomes.

    Returns:
        Dict with full record or error.
    """
    if source not in VALID_SOURCES:
        return {"error": f"Invalid source '{source}'. Must be one of: {sorted(VALID_SOURCES)}"}

    if source == "task_outcomes":
        row = conn.execute(
            "SELECT * FROM task_outcomes WHERE task_id = ?", (str(pattern_id),)
        ).fetchone()
    else:
        row = conn.execute(f"SELECT * FROM {source} WHERE id = ?", (pattern_id,)).fetchone()

    if row is None:
        return {"error": f"Not found: {source} id={pattern_id}"}

    result = dict(row)
    # Truncate narrative if very long
    if "narrative" in result and result["narrative"] and len(result["narrative"]) > 500:
        result["narrative"] = result["narrative"][:500] + "... [truncated]"

    # Boost access on detail view
    _boost_access(conn, source, pattern_id)
    conn.commit()

    return {"source": source, "record": result}


# ---------------------------------------------------------------------------
# thinking_os_promote
# ---------------------------------------------------------------------------


def memory_promote(
    conn: sqlite3.Connection,
    *,
    pattern_id: int,
    target: str,
    memory_dir: str,
) -> dict:
    """Promote a learned pattern to a rule or feedback memory file.

    Args:
        conn: SQLite connection.
        pattern_id: ID in learned_patterns table.
        target: One of: feedback, rule.
        memory_dir: Path to the memory directory for file creation.

    Returns:
        Dict with status and file path.
    """
    if target not in VALID_PROMOTE_TARGETS:
        return {
            "error": f"Invalid target '{target}'. Must be one of: {sorted(VALID_PROMOTE_TARGETS)}"
        }

    row = conn.execute("SELECT * FROM learned_patterns WHERE id = ?", (pattern_id,)).fetchone()

    if row is None:
        return {"error": f"Pattern not found: id={pattern_id}"}

    pattern_data = dict(row)

    if pattern_data.get("confidence", 0) < 0.3:
        return {
            "error": f"Pattern confidence too low ({pattern_data['confidence']:.2f}). Minimum 0.3 for promotion."
        }

    # Build file content
    slug = f"pattern_{pattern_id}"
    domain = pattern_data.get("domain", "general") or "general"

    if target == "feedback":
        filename = f"feedback_{slug}.md"
        content = (
            f"---\n"
            f"name: {slug}\n"
            f"description: Auto-promoted pattern from thinking_os (confidence: {pattern_data['confidence']:.2f})\n"
            f"type: feedback\n"
            f"---\n\n"
            f"{pattern_data['pattern']}\n\n"
            f"**Why:** Observed {pattern_data.get('times_validated', 0)} times validated, "
            f"{pattern_data.get('times_violated', 0)} times violated. "
            f"Domain: {domain}.\n\n"
            f"**How to apply:** When working on {domain} tasks, apply this pattern.\n"
        )
    else:  # rule
        filename = f"learned_{slug}.md"
        content = (
            f"# Learned Rule: {slug}\n\n"
            f"> Auto-promoted from thinking_os pattern #{pattern_id} "
            f"(confidence: {pattern_data['confidence']:.2f})\n\n"
            f"{pattern_data['pattern']}\n\n"
            f"Domain: {domain}\n"
            f"Evidence: {pattern_data.get('times_validated', 0)} validations, "
            f"{pattern_data.get('times_violated', 0)} violations\n"
        )

    # Update promoted_to in DB
    conn.execute(
        "UPDATE learned_patterns SET promoted_to = ? WHERE id = ?",
        (f"{target}:{filename}", pattern_id),
    )
    conn.commit()

    return {
        "status": "promoted",
        "target": target,
        "filename": filename,
        "content": content,
        "pattern_id": pattern_id,
    }
