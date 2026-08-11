"""Consolidation and generalization over already-mined patterns.

Extraction discovers patterns; this module keeps the corpus honest afterwards —
collapsing duplicates, folding semantic near-clones, and surfacing generalizable
lesson clusters as human-review drafts. It never writes a rule: abstraction stays
human-gated.
"""

from __future__ import annotations

import hashlib
import logging
import sqlite3

logger = logging.getLogger("thinking_os.learning")

try:  # package import
    from ._learning_store import _derive_project_root, _pattern_identity
except ImportError:  # flat import
    from _learning_store import (  # type: ignore[no-redef,import-not-found]
        _derive_project_root,
        _pattern_identity,
    )


def _collapse_duplicate_patterns(conn: sqlite3.Connection) -> int:
    # Self-healing one-shot: merge legacy count-snapshot duplicates that the
    # previously exact-text dedup let accumulate. Idempotent — once each
    # (identity, domain) group is a single row, this is a no-op. Returns the
    # number of rows deleted.
    rows = conn.execute(
        "SELECT id, pattern, domain, confidence, times_seen, times_validated FROM learned_patterns"
    ).fetchall()
    groups: dict[tuple[str, object], list] = {}
    for r in rows:
        groups.setdefault((_pattern_identity(r["pattern"]), r["domain"]), []).append(r)
    removed = 0
    for members in groups.values():
        if len(members) < 2:
            continue
        # Survivor = the most-established row by occurrences; fold BOTH counters so
        # neither the occurrence total (times_seen) nor real validations are lost.
        survivor = max(members, key=lambda m: ((m["times_seen"] or 0), m["confidence"], m["id"]))
        losers = [m["id"] for m in members if m["id"] != survivor["id"]]
        conn.execute(
            "UPDATE learned_patterns SET pattern = ?, confidence = ?, times_seen = ?, "
            "times_validated = ?, last_validated = CURRENT_TIMESTAMP WHERE id = ?",
            (
                survivor["pattern"],
                max(m["confidence"] for m in members),
                sum((m["times_seen"] or 0) for m in members) + len(losers),
                sum((m["times_validated"] or 0) for m in members),
                survivor["id"],
            ),
        )
        conn.executemany("DELETE FROM learned_patterns WHERE id = ?", [(i,) for i in losers])
        removed += len(losers)
    return removed


def _consolidate_semantic_duplicates(
    conn: sqlite3.Connection, *, threshold: float = 0.85, dry_run: bool = False
) -> int:
    # Survivor = highest (confidence, times_seen, oldest id); loser's access_count
    # + times_seen + times_validated fold in before delete. No-op without embeddings.
    try:
        from embeddings import cosine_similarity, is_available
    except ImportError:
        return 0
    if not is_available():
        return 0
    try:
        rows = conn.execute(
            "SELECT lp.id, lp.confidence, lp.times_seen, lp.times_validated, lp.access_count, e.embedding "
            "FROM learned_patterns lp JOIN embeddings e "
            "  ON e.source_table = 'learned_patterns' AND e.source_id = lp.id "
            "WHERE lp.promoted_to IS NULL AND lp.archived_at IS NULL"
        ).fetchall()
    except sqlite3.OperationalError as exc:
        logger.debug("semantic consolidation skipped: %s", exc)
        return 0

    items = [dict(r) for r in rows if r["embedding"]]
    if len(items) < 2:
        return 0
    # Stronger row first → it becomes the survivor of any similar pair.
    items.sort(key=lambda x: (-(x["confidence"] or 0.0), -(x["times_seen"] or 0), x["id"]))

    removed: set[int] = set()
    merged = 0
    for i, survivor in enumerate(items):
        if survivor["id"] in removed:
            continue
        cands = [c for c in items[i + 1 :] if c["id"] not in removed]
        if not cands:
            continue
        scores = cosine_similarity(survivor["embedding"], [c["embedding"] for c in cands])
        for cand, score in zip(cands, scores, strict=False):
            if score < threshold:
                continue
            if not dry_run:
                conn.execute(
                    "UPDATE learned_patterns SET access_count = COALESCE(access_count, 0) + ?, "
                    "times_seen = COALESCE(times_seen, 0) + ?, "
                    "times_validated = COALESCE(times_validated, 0) + ? WHERE id = ?",
                    (
                        cand["access_count"] or 0,
                        cand["times_seen"] or 0,
                        cand["times_validated"] or 0,
                        survivor["id"],
                    ),
                )
                conn.execute("DELETE FROM learned_patterns WHERE id = ?", (cand["id"],))
                conn.execute(
                    "DELETE FROM embeddings WHERE source_table = 'learned_patterns' AND source_id = ?",
                    (cand["id"],),
                )
            removed.add(cand["id"])
            merged += 1
    return merged


def _format_generalize_draft(cluster: list[dict]) -> str:
    lines = [
        "---",
        "type: feedback",
        "status: draft",
        f"lessons: {len(cluster)}",
        "---",
        "",
        f"# Generalize {len(cluster)} related lessons",
        "",
        "These lessons recur on a shared theme. Consider distilling ONE general",
        "rule and promoting it — this is a HUMAN-REVIEW draft; the system never",
        "auto-writes rules.",
        "",
        "## Member lessons",
    ]
    lines += [f"- (#{c['id']}) {c['pattern']}" for c in cluster]
    lines += [
        "",
        "## Suggested action",
        "- If they share a root cause, write one rule that covers all of them.",
        "- Then `cos_promote(pattern_id=<strongest>, target='feedback'|'rule')`.",
    ]
    return "\n".join(lines) + "\n"


def generalize_lessons(
    conn: sqlite3.Connection, *, min_cluster: int = 3, sim_threshold: float = 0.6
) -> dict:
    """Surface generalizable lesson clusters as human-review drafts (B3).

    Greedily clusters `lesson` patterns by embeddings cosine; when >= min_cluster
    related lessons share a theme, writes a feedback draft to
    `.coding-os/memory/drafts/` suggesting one general rule. NO LLM, NEVER writes
    to rules/docs — abstraction stays human-gated. Deduped by cluster signature.
    Returns {"drafts": [filenames]}. No-op without embeddings / project root.
    """
    try:
        from embeddings import cosine_similarity, is_available
    except ImportError:
        return {"drafts": []}
    if not is_available():
        return {"drafts": []}
    root = _derive_project_root(conn)
    if root is None:
        return {"drafts": []}
    try:
        rows = conn.execute(
            "SELECT lp.id, lp.pattern, e.embedding FROM learned_patterns lp "
            "JOIN embeddings e ON e.source_table = 'learned_patterns' AND e.source_id = lp.id "
            "WHERE lp.memory_type = 'lesson' AND lp.archived_at IS NULL AND lp.promoted_to IS NULL"
        ).fetchall()
    except sqlite3.OperationalError as exc:
        logger.debug("generalize_lessons skipped: %s", exc)
        return {"drafts": []}

    items = [dict(r) for r in rows if r["embedding"]]
    if len(items) < min_cluster:
        return {"drafts": []}

    drafts_dir = root / ".coding-os" / "memory" / "drafts"
    clustered: set[int] = set()
    drafts: list[str] = []
    for seed in items:
        if seed["id"] in clustered:
            continue
        rest = [c for c in items if c["id"] != seed["id"] and c["id"] not in clustered]
        if not rest:
            break
        scores = cosine_similarity(seed["embedding"], [c["embedding"] for c in rest])
        cluster = [seed] + [c for c, s in zip(rest, scores, strict=False) if s >= sim_threshold]
        if len(cluster) < min_cluster:
            continue
        for c in cluster:
            clustered.add(c["id"])
        sig = "-".join(str(c["id"]) for c in sorted(cluster, key=lambda x: x["id"]))
        fname = f"generalize-{hashlib.sha1(sig.encode()).hexdigest()[:10]}.md"
        target = drafts_dir / fname
        if target.exists():
            continue
        try:
            drafts_dir.mkdir(parents=True, exist_ok=True)
            target.write_text(_format_generalize_draft(cluster), encoding="utf-8")
            drafts.append(fname)
        except OSError as exc:
            logger.debug("generalize draft write failed: %s", exc)
    return {"drafts": drafts}
