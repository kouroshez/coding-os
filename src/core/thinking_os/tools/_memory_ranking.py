"""Ranking primitives for memory retrieval — scoring, fusion, and diversity.

The 5-signal score decides *how good* a candidate is; Reciprocal Rank Fusion
merges the lexical and semantic orderings without needing comparable scores;
MMR then trades a little relevance for coverage so five near-identical rows
never fill the whole result.
"""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone

# 5-signal weights
W_RELEVANCE = 0.30
W_CONFIDENCE = 0.25
W_RECENCY = 0.15
W_IMPACT = 0.15
W_ACCESS = 0.15

# Reciprocal Rank Fusion constant (standard k) + MMR diversity trade-off.
RRF_K = 60
MMR_LAMBDA = 0.7


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


def _fts5_safe_query(query: str) -> str:
    # Quote each whitespace token as a phrase so FTS5 metacharacters (:, ", *,
    # parens, and bareword AND/OR/NEAR) are literal, not operators. An unescaped
    # natural-language query raised OperationalError → silent whole-phrase LIKE
    # 0-hit fallback.
    return " ".join('"' + t.replace('"', '""') + '"' for t in query.split() if t)


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
            key=lambda c: (
                lam * rel[id(c)]
                - (1.0 - lam)
                * max((_jaccard(sig[id(c)], sig[id(s)]) for s in selected), default=0.0)
            ),
        )
        selected.append(best)
        pool = [c for c in pool if c is not best]
    return selected
