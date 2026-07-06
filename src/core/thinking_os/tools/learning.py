"""
Thinking OS — MCP learning tools.

Pattern mining and rule suggestion:
  - cos_learn_extract: discover patterns from task outcomes
  - cos_learn_suggest: return relevant patterns for current context
  - cos_learn_validate: confirm/deny a pattern's usefulness
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger("thinking_os.learning")

MIN_DATA_THRESHOLD = 3  # minimum task outcomes before extraction

# self-validation throttle window. Same (session, pattern)
# positive validation is ignored within this window. 1h is long enough to
# cover a continuous task loop but short enough that legitimate re-use
# across sessions isn't suppressed.
_THROTTLE_WINDOW_SECONDS = 3600


def _read_session_id_for_validate() -> str:
    import os
    from pathlib import Path

    state_dir = Path(os.environ.get("COS_STATE_DIR", ".coding-os"))
    agent_dir_env = os.environ.get("COS_AGENT_DIR")
    if agent_dir_env:
        f = Path(agent_dir_env) / "session-id"
        if f.exists():
            sid = f.read_text().strip()
            if sid:
                return sid
    agent = os.environ.get("COS_AGENT", "")
    if not agent:
        marker = state_dir / ".agent"
        if marker.exists():
            agent = marker.read_text().strip()
    if agent:
        f = state_dir / agent / "session-id"
        if f.exists():
            sid = f.read_text().strip()
            if sid:
                return sid
    flat = state_dir / "session-id"
    if flat.exists():
        sid = flat.read_text().strip()
        if sid:
            return sid
    return "ses-unknown"


def _has_recent_validation(
    conn: sqlite3.Connection,
    session_id: str,
    pattern_id: int,
) -> bool:
    try:
        row = conn.execute(
            "SELECT 1 FROM pattern_validations "
            "WHERE session_id = ? AND pattern_id = ? AND was_helpful = 1 "
            "  AND created_at >= datetime('now', '-' || ? || ' seconds') "
            "LIMIT 1",
            (session_id, pattern_id, _THROTTLE_WINDOW_SECONDS),
        ).fetchone()
    except sqlite3.OperationalError:
        return False
    return row is not None


def _log_validation(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    pattern_id: int,
    was_helpful: bool,
    was_throttled: bool,
) -> None:
    # Fire-and-forget — never raises (audit row, must not break validation).
    try:
        conn.execute(
            "INSERT INTO pattern_validations "
            "(session_id, pattern_id, was_helpful, was_throttled) "
            "VALUES (?, ?, ?, ?)",
            (session_id, pattern_id, 1 if was_helpful else 0, 1 if was_throttled else 0),
        )
        conn.commit()
    except sqlite3.OperationalError as exc:
        logger.debug("_log_validation skipped: %s", exc)


# ---------------------------------------------------------------------------
# Confidence formulas (brain-inspired)
# ---------------------------------------------------------------------------


def boost_success(conf: float) -> float:
    """LTP with diminishing returns — validated pattern gets stronger."""
    return min(0.95, conf + 0.1 * (1.0 - conf))


def penalize_failure(conf: float) -> float:
    """LTD proportional — violated pattern weakens."""
    return max(0.1, conf - 0.15 * conf)


# ---------------------------------------------------------------------------
# cos_learn_extract
# ---------------------------------------------------------------------------


def learn_extract(
    conn: sqlite3.Connection,
    *,
    min_occurrences: int = 3,
) -> dict:
    """Scan task_outcomes to discover recurring patterns.

    Detects:
      - domain_rework: domains with high rework rates
      - skill_correlation: skills correlated with success/failure
      - complexity_mismatch: tasks classified too low/high

    Args:
        conn: SQLite connection.
        min_occurrences: Minimum occurrences to consider a pattern.

    Returns:
        Dict with extracted patterns and stats.
    """
    min_occurrences = max(1, min_occurrences)

    # Check data threshold
    total_outcomes = conn.execute("SELECT COUNT(*) FROM task_outcomes").fetchone()[0]
    if total_outcomes < MIN_DATA_THRESHOLD:
        return {
            "status": "insufficient_data",
            "message": f"Insufficient data (need {MIN_DATA_THRESHOLD}+ outcomes, have {total_outcomes})",
            "extracted": [],
        }

    extracted: list[dict] = []

    # Heal any legacy count-snapshot duplicates before mining so the upsert
    # below updates a single survivor row per fact.
    _collapse_duplicate_patterns(conn)

    # --- Domain rework patterns ---
    domain_rows = conn.execute(
        "SELECT domain, COUNT(*) AS total, "
        "SUM(CASE WHEN outcome = 'rework' THEN 1 ELSE 0 END) AS rework_count "
        "FROM task_outcomes "
        "GROUP BY domain "
        "HAVING rework_count >= ?",
        (min_occurrences,),
    ).fetchall()

    for row in domain_rows:
        d = dict(row)
        rework_rate = d["rework_count"] / d["total"] if d["total"] > 0 else 0
        if rework_rate < 0.2:
            continue  # not significant enough
        confidence = min(0.9, d["rework_count"] / (d["total"] * 2))
        pattern_text = (
            f"{d['domain']} domain has {rework_rate:.0%} rework rate "
            f"({d['rework_count']}/{d['total']} tasks)"
        )
        extracted.append(
            _upsert_pattern(
                conn,
                pattern=pattern_text,
                memory_type="pattern",
                domain=d["domain"],
                source="learn_extract",
                confidence=confidence,
                concepts=json.dumps([d["domain"].lower(), "rework", "domain_pattern"]),
            )
        )

    # --- Skill correlation patterns ---
    skill_rows = conn.execute(
        "SELECT skills_used, outcome, COUNT(*) AS count "
        "FROM task_outcomes "
        "WHERE skills_used IS NOT NULL AND skills_used != '' "
        "GROUP BY skills_used, outcome "
        "HAVING count >= ?",
        (min_occurrences,),
    ).fetchall()

    for row in skill_rows:
        d = dict(row)
        if d["outcome"] == "rework":
            confidence = min(0.9, d["count"] / 10.0)
            pattern_text = (
                f"Skill '{d['skills_used']}' correlates with rework ({d['count']} occurrences)"
            )
            extracted.append(
                _upsert_pattern(
                    conn,
                    pattern=pattern_text,
                    memory_type="pattern",
                    domain=None,
                    source="learn_extract",
                    confidence=confidence,
                    concepts=json.dumps(["skill", d["skills_used"], "rework"]),
                )
            )

    # --- Complexity mismatch patterns ---
    mismatch_rows = conn.execute(
        "SELECT complexity, outcome, COUNT(*) AS count "
        "FROM task_outcomes "
        "WHERE outcome = 'rework' "
        "GROUP BY complexity "
        "HAVING count >= ?",
        (min_occurrences,),
    ).fetchall()

    for row in mismatch_rows:
        d = dict(row)
        # Check if CLEAR tasks frequently rework (likely underclassified)
        if d["complexity"] == "CLEAR" and d["count"] >= min_occurrences:
            total_clear = conn.execute(
                "SELECT COUNT(*) FROM task_outcomes WHERE complexity = 'CLEAR'"
            ).fetchone()[0]
            if total_clear > 0:
                rate = d["count"] / total_clear
                if rate > 0.3:
                    confidence = min(0.9, rate)
                    pattern_text = (
                        f"CLEAR tasks rework at {rate:.0%} — may be underclassified "
                        f"({d['count']}/{total_clear})"
                    )
                    extracted.append(
                        _upsert_pattern(
                            conn,
                            pattern=pattern_text,
                            memory_type="decision",
                            domain=None,
                            source="learn_extract",
                            confidence=confidence,
                            concepts=json.dumps(["complexity", "classification", "mismatch"]),
                        )
                    )

    # --- Success baseline patterns (positive-signal mining) ---
    # A healthy success-only history must still yield learnable patterns —
    # without this the loop can ONLY learn from failure, so a project that
    # rarely reworks produces zero patterns forever. Mine per-domain and
    # per-skill success so cos_learn_suggest has positive anchors to rank.
    # Variance gate: a success-rate stat only informs when the corpus has a
    # non-success outcome to contrast against. On a monotone-success corpus
    # every "X succeeds 100%" is a tautology — skip both stat branches.
    # See docs/engineering/learning-extraction.md § Variance gate.
    _has_variance = (
        conn.execute("SELECT COUNT(*) FROM task_outcomes WHERE outcome != 'success'").fetchone()[0]
        > 0
    )

    success_domain_rows = (
        conn.execute(
            "SELECT domain, COUNT(*) AS total, "
            "SUM(CASE WHEN outcome = 'success' THEN 1 ELSE 0 END) AS success_count "
            "FROM task_outcomes WHERE domain IS NOT NULL AND domain != '' "
            "GROUP BY domain HAVING success_count >= ?",
            (min_occurrences,),
        ).fetchall()
        if _has_variance
        else []
    )
    for row in success_domain_rows:
        d = dict(row)
        rate = d["success_count"] / d["total"] if d["total"] else 0
        confidence = min(0.85, 0.4 + d["success_count"] / 20.0)
        pattern_text = (
            f"{d['domain']} domain succeeds at {rate:.0%} "
            f"({d['success_count']}/{d['total']} tasks) — reliable baseline"
        )
        extracted.append(
            _upsert_pattern(
                conn,
                pattern=pattern_text,
                # 'stat' (not a belief): a success rate is observability, not a
                # lesson — excluded from the digest + cos_learn_suggest so it
                # never masquerades as a learning. See learning-extraction.md.
                memory_type="stat",
                domain=d["domain"],
                source="learn_extract",
                confidence=confidence,
                concepts=json.dumps([d["domain"].lower(), "success", "baseline", "stat"]),
            )
        )

    skill_success_rows = (
        conn.execute(
            "SELECT skills_used, COUNT(*) AS count "
            "FROM task_outcomes "
            "WHERE outcome = 'success' AND skills_used IS NOT NULL AND skills_used != '' "
            "GROUP BY skills_used HAVING count >= ?",
            (min_occurrences,),
        ).fetchall()
        if _has_variance
        else []
    )
    for row in skill_success_rows:
        d = dict(row)
        confidence = min(0.8, 0.4 + d["count"] / 20.0)
        pattern_text = (
            f"Skill set '{d['skills_used']}' correlates with success ({d['count']} tasks)"
        )
        extracted.append(
            _upsert_pattern(
                conn,
                pattern=pattern_text,
                memory_type="stat",  # observability, not a belief — see above
                domain=None,
                source="learn_extract",
                confidence=confidence,
                concepts=json.dumps(["skill", "success", "correlation", "stat"]),
            )
        )

    # --- Failure anatomy patterns (v25) ---
    # Mine structured backtrack_events for recurring root_cause patterns.
    # Only runs when anatomy columns are present (migration v25).
    try:
        from tools.cognition import CANONICAL_REMEDIES

        anat_rows = conn.execute(
            # Anatomy pairs a recurring cause with its remedy — the one the agent
            # recorded, else the canonical corrective action for that cause. Never
            # a bare count (learning-extraction.md § Anatomy from backtracks).
            "SELECT root_cause, COUNT(*) AS cnt, "
            "       GROUP_CONCAT(DISTINCT from_formula) AS formulas, "
            "       MAX(corrective_action) AS remedy "
            "FROM backtrack_events "
            "WHERE root_cause IS NOT NULL "
            "GROUP BY root_cause "
            "HAVING cnt >= ?",
            (min_occurrences,),
        ).fetchall()
        for row in anat_rows:
            d = dict(row)
            remedy = (d["remedy"] or "").strip() or CANONICAL_REMEDIES.get(d["root_cause"], "")
            if not remedy:
                continue  # no recorded nor canonical remedy — skip, never a bare count
            confidence = min(0.85, d["cnt"] / 20.0 + 0.3)
            formulas_str = d["formulas"] or ""
            pattern_text = (
                f"Recurring backtrack root cause '{d['root_cause']}' "
                f"({d['cnt']} occurrences"
                + (f"; formulas: {formulas_str[:60]}" if formulas_str else "")
                + f") → {remedy[:160]}"
            )
            extracted.append(
                _upsert_pattern(
                    conn,
                    pattern=pattern_text,
                    memory_type="failure",
                    domain=None,
                    source="learn_extract",
                    confidence=confidence,
                    concepts=json.dumps(["failure", d["root_cause"], "backtrack"]),
                )
            )
    except Exception as exc:  # backtrack_events or anatomy columns absent — fire-and-forget
        logger.debug("learn_extract: failure anatomy skipped: %s", exc)

    # --- Friction lessons ---
    # The abundant, automatic learning signal: hook BLOCKs and tool failures
    # the agent emits every session. Mined into actionable
    # `lesson` patterns so the loop learns from mistakes — not just success
    # statistics. Contract: docs/engineering/learning-extraction.md.
    try:
        distill_budget = int(os.environ.get("COS_DISTILL_MAX_CLUSTERS", "20"))
    except ValueError:
        distill_budget = 20
    distill_state = {"remaining": max(0, distill_budget)}
    extracted.extend(
        _mine_friction_lessons(
            conn, min_occurrences=min_occurrences, distill_state=distill_state
        )
    )
    # Hook BLOCKs live in the activity log (not observations) on Claude — mine
    # them too so the richest friction signal becomes a lesson.
    extracted.extend(
        _mine_hook_block_lessons(
            conn, min_occurrences=min_occurrences, distill_state=distill_state
        )
    )
    # fix:/revert: commit subjects — the real engineering-lesson signal that
    # reasoning records in git history, not in any friction table (§5).
    extracted.extend(_mine_commit_lessons(conn, min_occurrences=min_occurrences))

    # Generalize related lessons into human-review drafts (B3). Fire-and-forget;
    # writes only when a NEW cluster forms (deduped). Never blocks extraction.
    try:
        generalize_lessons(conn)
    except Exception as exc:
        logger.debug("generalize_lessons skipped: %s", exc)

    conn.commit()
    return {
        "status": "ok",
        "total_outcomes_analyzed": total_outcomes,
        "extracted": extracted,
    }


_SOURCE_TO_PROVENANCE: dict[str, str] = {
    "learn_extract": "extracted_from_outcome",
    "friction": "extracted_from_observation",
    "commit": "extracted_from_commit",
    "breakthrough": "agent_self",
    "manual": "user_directive",
    "import": "imported",
}


# Volatile counters embedded in mined pattern text — the running task
# count grows every extraction run, so it must NOT be part of a pattern's
# identity or each run mints a new snapshot row instead of updating one.
_IDENTITY_COUNT_RE = re.compile(r"\(\d+(?:/\d+)?\s*(?:tasks?|occurrences?)[^)]*\)", re.IGNORECASE)
_IDENTITY_RATIO_RE = re.compile(r"\(\d+/\d+\)")
_IDENTITY_PCT_RE = re.compile(r"\d+(?:\.\d+)?%")


def _pattern_identity(text: str) -> str:
    # Count-agnostic dedup key: strip the running counts / percentages so a
    # re-mined fact ("INFRA succeeds … (40/40)" → "(83/83)") maps to the
    # SAME row. The displayed `pattern` keeps the live numbers; only the
    # identity ignores them.
    t = _IDENTITY_COUNT_RE.sub("", text)
    t = _IDENTITY_RATIO_RE.sub("", t)
    t = _IDENTITY_PCT_RE.sub("", t)
    return " ".join(t.split()).lower()


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
        for cand, score in zip(cands, scores):
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
        cluster = [seed] + [c for c, s in zip(rest, scores) if s >= sim_threshold]
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


def _upsert_pattern(
    conn: sqlite3.Connection,
    *,
    pattern: str,
    memory_type: str,
    domain: str | None,
    source: str,
    confidence: float,
    concepts: str,
    provenance: str | None = None,
    distill_fingerprint: str | None = None,
    evidence_json: str | None = None,
) -> dict:
    # Sanitizer runs before any DB write; a rejected pattern returns
    # {"action": "rejected", ...} with no row touched. provenance keeps
    # agent_self writes distinguishable from mined data for sycophancy analysis.
    if provenance is None:
        provenance = _SOURCE_TO_PROVENANCE.get(source, "agent_self")
    from sanitizer import sanitize_write

    p_sr = sanitize_write(
        "pattern",
        pattern,
        actor="learning._upsert_pattern",
        source_table="learned_patterns",
        conn=conn,
    )
    if not p_sr.ok:
        return {
            "id": None,
            "pattern": (pattern or "")[:60],
            "confidence": 0.0,
            "action": "rejected",
            "reason": p_sr.reason,
        }
    pattern = p_sr.cleaned

    # Match on a count-agnostic identity, not exact text: a re-mined fact
    # whose running count grew ("(40/40)" → "(83/83)") is the SAME pattern
    # and must update its row, not insert a snapshot. The table is small, so
    # canonicalise candidate rows in the same domain.
    identity = _pattern_identity(pattern)
    existing = None
    if distill_fingerprint:
        try:
            existing = conn.execute(
                "SELECT id, pattern, confidence, times_validated FROM learned_patterns "
                "WHERE distill_fingerprint = ?",
                (distill_fingerprint,),
            ).fetchone()
        except sqlite3.OperationalError:
            existing = None
    if existing is None:
        for cand in conn.execute(
            "SELECT id, pattern, confidence, times_validated FROM learned_patterns WHERE domain IS ?",
            (domain,),
        ):
            if _pattern_identity(cand["pattern"]) == identity:
                existing = cand
                break

    if existing:
        # Update confidence (take the higher) and refresh the displayed text
        # to the latest counts. Each re-mining is a recurrence, so bump
        # times_seen — the occurrence count; times_validated stays reserved for
        # real validation events (_boost_success / _log_validation) so trust
        # ranking is not inflated by mere re-extraction.
        new_conf = max(existing["confidence"], confidence)
        # Re-extraction is a positive signal: refresh recency AND revive a row a
        # prior decay run archived. A REAL promotion (promoted_to='rule:…' /
        # 'feedback:…') survives the re-mine — the knowledge now lives in the
        # rule layer, and un-promoting it would put the same fact in two places.
        conn.execute(
            # Refresh memory_type too: a re-mine reclassifies a row whose class
            # changed (e.g. a legacy success baseline minted as 'pattern' becomes
            # 'stat'), so old garbage reclassifies on the next loop run.
            "UPDATE learned_patterns SET pattern = ?, memory_type = ?, confidence = ?, "
            "times_seen = COALESCE(times_seen, 0) + 1, last_validated = CURRENT_TIMESTAMP, "
            "last_accessed_at = CURRENT_TIMESTAMP, "
            "promoted_to = CASE WHEN COALESCE(promoted_to, '') IN ('', 'archived') "
            "  THEN NULL ELSE promoted_to END, "
            "archived_at = CASE WHEN COALESCE(promoted_to, '') IN ('', 'archived') "
            "  THEN NULL ELSE archived_at END, "
            "distill_fingerprint = COALESCE(?, distill_fingerprint), "
            "evidence_json = COALESCE(?, evidence_json) "
            "WHERE id = ?",
            (pattern, memory_type, new_conf, distill_fingerprint, evidence_json, existing["id"]),
        )
        pattern_id = existing["id"]
        result = {"id": pattern_id, "pattern": pattern, "confidence": new_conf, "action": "updated"}
    else:
        # Stamp last_validated/last_accessed_at at creation so a fresh pattern's age is 0.
        # Otherwise run_decay reads _days_since(NULL)→999d and archives it on the FIRST run.
        cursor = conn.execute(
            "INSERT INTO learned_patterns "
            "(pattern, memory_type, domain, source, confidence, concepts, provenance, "
            "distill_fingerprint, evidence_json, last_validated, last_accessed_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            (
                pattern,
                memory_type,
                domain,
                source,
                confidence,
                concepts,
                provenance,
                distill_fingerprint,
                evidence_json,
            ),
        )
        pattern_id = cursor.lastrowid
        result = {
            "id": pattern_id,
            "pattern": pattern,
            "confidence": confidence,
            "action": "created",
        }

    # RAG: embed the pattern for semantic search.
    # Suppressed because embeddings are optional enrichment — the upsert
    # itself must succeed even when rag extras / v5 schema are unavailable.
    _embed_pattern_safe(conn, pattern_id, pattern, concepts)

    return result


def _embed_pattern_safe(
    conn: sqlite3.Connection,
    pattern_id: int,
    pattern: str,
    concepts: str,
) -> None:
    # Fire-and-forget: embeddings are optional enrichment — never fail the upsert.
    try:
        from embeddings import upsert_embedding
    except ImportError as exc:
        logger.debug("Skipping pattern embedding (module unavailable): %s", exc)
        return
    try:
        text_to_embed = " ".join(filter(None, [pattern, concepts]))
        upsert_embedding(conn, "learned_patterns", pattern_id, text_to_embed)
    except sqlite3.OperationalError as exc:
        logger.debug("Skipping pattern embedding (table missing): %s", exc)
    except Exception as exc:  # pragma: no cover
        logger.debug("Skipping pattern embedding (unexpected): %s", exc)


# ---------------------------------------------------------------------------
# Friction lesson mining (the real learning signal)
# ---------------------------------------------------------------------------

# A friction event seen this many times is already worth a rule. Lower than the
# stat threshold (3) because each failure is individually high-value, and never
# higher than the caller's floor.
_FRICTION_MIN_OCCURRENCES = 2

# Plain-language corrective hint per friction kind — kept beginner-readable.
_FRICTION_HINTS: dict[str, str] = {
    "hook_block": "satisfy the blocked rule before retrying the action",
    "schema_mismatch": "match the required output schema exactly before resubmitting",
    "error": "fix the failing precondition before retrying",
}

# Normalisers that turn a volatile failure message into a stable cluster key:
# absolute paths → basename, TASK ids and long hashes → placeholders.
_ABS_PATH_RE = re.compile(r"(?:/[^\s'\":,]+)+/([^\s'\":/,]+)")
_TASKID_RE = re.compile(r"TASK-\d+", re.IGNORECASE)
_LONGHEX_RE = re.compile(r"\b[0-9a-f]{8,}\b", re.IGNORECASE)
_NONWORD_RE = re.compile(r"[^a-z0-9<>_.-]+")


def _friction_kind(title: str, narrative: str, memory_type: str) -> str:
    # Most-specific signal first. hook_block is detected by the capture's
    # memory_type or a leading "BLOCKED" — NOT a loose "blocked" substring,
    # which appears in unrelated remediation text (e.g. "--to blocked").
    title_l = (title or "").lower()
    narr_l = (narrative or "").lower()
    if "does not match required schema" in narr_l or ("schema" in narr_l and "property" in narr_l):
        return "schema_mismatch"
    if memory_type == "hook_block" or narr_l.startswith("blocked") or "[blocked]" in title_l:
        return "hook_block"
    return "error"


def _clean_failure_text(text: str) -> str:
    line = (text or "").strip().split("\n", 1)[0]
    line = _ABS_PATH_RE.sub(r"\1", line)
    line = _TASKID_RE.sub("TASK-N", line)
    line = _LONGHEX_RE.sub("<hash>", line)
    return " ".join(line.split())[:200]


def _failure_cluster_key(display: str) -> str:
    norm = re.sub(r"\d+", "N", display.lower())
    words = [w for w in _NONWORD_RE.split(norm) if w]
    return " ".join(words[:8])


# Substrings that mark an `error` observation as a tool-fumble or expected
# refusal — the agent tripping over its own tooling, never an engineering lesson.
# See learning-extraction.md § Noise filter.
_NOISE_FAILURE_MARKERS: tuple[str, ...] = (
    "eisdir",
    "illegal operation on a directory",
    "file does not exist",
    "no such file or directory",
    "refusing to write through symlink",
    "structuredoutput",  # workflow-internal schema fumble, not a code lesson
    "validation error for cos_",  # agent mis-called an MCP tool schema — fumble
    "validation errors for cos_",
    "exceeds maximum allowed",  # oversized Read/tool payload — operational refusal
    "scrape aborted",  # external scraping engine refusal — environment, not code
    "scraping engines failed",
    "mcp error -",  # raw MCP transport error — infrastructure, not a lesson
)


def _is_noise_failure(display: str) -> bool:
    low = display.lower()
    return any(marker in low for marker in _NOISE_FAILURE_MARKERS)


# Known internal/model jargon → plain language, so a lesson reads for a novice
# (XAI/PAIR: speak the user's language, not the model's). Applied longest-first.
_JARGON_TRANSLATIONS: tuple[tuple[str, str], ...] = (
    (
        "predicates_unsatisfied: no evidencebundle for predicates ['coverage_100']",
        "ended a 'fix everything' task without recording proof every case was handled",
    ),
    ("predicates_unsatisfied", "ended the task without the required proof-of-completion"),
    ("no evidencebundle", "no proof-of-completion was recorded"),
    ("task_not_closed", "left a task open"),
    ("does not match required schema", "the output's shape did not match what was required"),
)


def _humanize_signature(display: str) -> str:
    out = display
    low = out.lower()
    for jargon, plain in _JARGON_TRANSLATIONS:
        idx = low.find(jargon)
        if idx != -1:
            out = out[:idx] + plain + out[idx + len(jargon) :]
            low = out.lower()
    return out


def pattern_tier(confidence: float, times_validated: int) -> str:
    """Confidence tier for a learned pattern — the single mapping used by the UI
    and digest. SSOT: learning-extraction.md § Confidence tier mapping.

    Trusted = confirmed repeatedly · Fading = decaying, up for re-validation ·
    Forming = seen, not yet confirmed.
    """
    conf = confidence or 0.0
    tv = times_validated or 0
    if conf >= 0.7 and tv >= 3:
        return "Trusted"
    if 0.2 <= conf <= 0.4 and tv >= 1:
        return "Fading"
    return "Forming"


def _distill_safe(**kwargs) -> dict | None:
    # Fire-and-forget: the distiller is optional enrichment — any failure
    # (module missing, dispatcher down, headless without auth) falls back to
    # the template producer.
    try:
        import distill

        if not distill.enabled():
            return None
        return distill.distill_cluster(**kwargs)
    except Exception as exc:
        logger.debug("distillation skipped: %s", exc)
        return None


def _adopt_legacy_template(conn: sqlite3.Connection, template_text: str, new_id: int) -> None:
    # A distilled lesson supersedes the template row for the same cluster:
    # fold the old counters in, then invalidate (archive), never delete.
    identity = _pattern_identity(template_text)
    for cand in conn.execute(
        "SELECT id, pattern, times_seen, times_validated, access_count FROM learned_patterns "
        "WHERE domain IS NULL AND COALESCE(promoted_to, '') != 'archived'",
    ):
        if cand["id"] == new_id or _pattern_identity(cand["pattern"]) != identity:
            continue
        conn.execute(
            "UPDATE learned_patterns SET times_seen = COALESCE(times_seen, 0) + ?, "
            "times_validated = times_validated + ?, access_count = access_count + ? "
            "WHERE id = ?",
            (cand["times_seen"] or 0, cand["times_validated"] or 0, cand["access_count"] or 0, new_id),
        )
        conn.execute(
            "UPDATE learned_patterns SET promoted_to = 'archived', "
            "archived_at = CURRENT_TIMESTAMP WHERE id = ?",
            (cand["id"],),
        )
        break


def _mint_friction_lesson(
    conn: sqlite3.Connection,
    *,
    kind: str,
    cluster_key: str,
    count: int,
    template_text: str,
    concepts: str,
    hook: str = "",
    rule: str = "",
    samples: list[str] | None = None,
    distill_state: dict | None = None,
) -> dict:
    # One write path for both friction miners: refresh an already-distilled
    # cluster for free, distill a new one under the per-run budget, or fall
    # back to the deterministic template.
    fingerprint = None
    try:
        import distill

        fingerprint = distill.cluster_fingerprint(kind, cluster_key)
    except Exception as exc:
        logger.debug("fingerprint unavailable: %s", exc)

    if fingerprint:
        try:
            row = conn.execute(
                "SELECT id, pattern FROM learned_patterns WHERE distill_fingerprint = ?",
                (fingerprint,),
            ).fetchone()
        except sqlite3.OperationalError:
            row = None
        if row:
            return _upsert_pattern(
                conn,
                pattern=row["pattern"],
                memory_type="lesson",
                domain=None,
                source="friction",
                confidence=0.5,
                concepts=concepts,
                provenance="llm_distilled",
                distill_fingerprint=fingerprint,
            )

    budget_left = bool(distill_state) and distill_state.get("remaining", 0) > 0
    if fingerprint and budget_left:
        distill_state["remaining"] -= 1
        distilled = _distill_safe(
            kind=kind, signature=cluster_key, count=count, hook=hook, rule=rule, samples=samples
        )
        if distilled:
            import distill

            result = _upsert_pattern(
                conn,
                pattern=distill.lesson_text(distilled),
                memory_type="lesson",
                domain=None,
                source="friction",
                confidence=0.5,
                concepts=concepts,
                provenance="llm_distilled",
                distill_fingerprint=fingerprint,
                evidence_json=json.dumps(
                    {"samples": distill.sanitize_samples(samples or []), "recurrences": count}
                ),
            )
            if result.get("id"):
                _adopt_legacy_template(conn, template_text, result["id"])
            return result

    return _upsert_pattern(
        conn,
        pattern=template_text,
        memory_type="lesson",
        domain=None,
        source="friction",
        confidence=min(0.85, 0.4 + count / 10.0),
        concepts=concepts,
    )


def _mine_friction_lessons(
    conn: sqlite3.Connection,
    *,
    min_occurrences: int = 3,
    distill_state: dict | None = None,
) -> list[dict]:
    # Fire-and-forget: a missing observations table/column never breaks extraction.
    floor = max(1, min(min_occurrences, _FRICTION_MIN_OCCURRENCES))
    try:
        rows = conn.execute(
            "SELECT title, narrative, memory_type, files_modified FROM observations "
            "WHERE memory_type IN ('hook_block', 'error') AND COALESCE(narrative, '') != '' "
            "  AND created_at >= datetime('now', '-' || ? || ' days')",
            (_LESSON_WINDOW_DAYS,),
        ).fetchall()
    except sqlite3.OperationalError as exc:
        logger.debug("friction mining skipped: %s", exc)
        return []

    clusters: dict[str, dict] = {}
    for row in rows:
        d = dict(row)
        # Screen title AND narrative: a StructuredOutput fumble carries the marker
        # in the title while the narrative reads like a generic schema error.
        if _is_noise_failure(f"{d['title'] or ''} {d['narrative'] or ''}"):
            continue  # tool-fumble / expected refusal — never a lesson
        display = _clean_failure_text(d["narrative"] or d["title"] or "")
        key = _failure_cluster_key(display)
        if not key:
            continue
        cluster = clusters.setdefault(
            key,
            {
                "count": 0,
                # store the humanized signature so the minted lesson reads plainly
                "display": _humanize_signature(display),
                "kind": _friction_kind(d["title"], d["narrative"], d["memory_type"]),
                "files": set(),  # source-file basenames → concepts, for JIT recall
                "samples": [],
            },
        )
        cluster["count"] += 1
        if len(cluster["samples"]) < 3:
            cluster["samples"].append(display)
        fm = d.get("files_modified") or ""
        if fm:
            cluster["files"].add(fm.rsplit("/", 1)[-1])

    lessons: list[dict] = []
    for key, cluster in clusters.items():
        if cluster["count"] < floor:
            continue
        hint = _FRICTION_HINTS.get(cluster["kind"], _FRICTION_HINTS["error"])
        # Count rendered as "(N occurrences)" so _pattern_identity strips it and
        # a re-mined cluster UPDATES its row instead of inserting a snapshot.
        pattern_text = (
            f"Recurring {cluster['kind'].replace('_', ' ')} "
            f"({cluster['count']} occurrences): {cluster['display']} → {hint}"
        )
        lessons.append(
            _mint_friction_lesson(
                conn,
                kind=cluster["kind"],
                cluster_key=key,
                count=cluster["count"],
                template_text=pattern_text,
                samples=cluster["samples"],
                distill_state=distill_state,
                # file:<basename> tokens key JIT recall on the friction's source
                # file (not basename-in-humanized-text, which never matched).
                concepts=json.dumps(
                    ["lesson", cluster["kind"], "friction"]
                    + [f"file:{b}" for b in sorted(cluster["files"])[:5] if b]
                ),
            )
        )
    return lessons


# A hook-log block line: "[<ts>] [<hook>] [block] … rule=<rule> …".
_BLOCK_LINE_RE = re.compile(
    r"^\[(?P<ts>[^\]]+)\]\s+\[(?P<hook>[^\]]+)\]\s+\[block\]\s*(?P<rest>.*)$"
)
_BLOCK_RULE_RE = re.compile(r"\brule=(\S+)")
# Recency window shared by both friction miners: a failure/block only counts as
# a recurring lesson if it recurs within this window. Old/resolved/renamed-rule
# failures age out (stop being re-confirmed) and decay instead of persisting.
_LESSON_WINDOW_DAYS = 90


def _hook_log_paths(conn: sqlite3.Connection) -> list[Path]:
    # Most-durable first: block-only log (survives the main log's cap) then the
    # main hook log. Env overrides win; otherwise derive from the project root.
    paths: list[Path] = []
    blk = os.environ.get("COS_HOOK_BLOCK_LOG")
    main = os.environ.get("COS_HOOK_LOG")
    if blk:
        paths.append(Path(blk))
    if main:
        paths.append(Path(main))
    if not paths:
        root = _derive_project_root(conn)
        if root:
            paths.append(root / ".coding-os" / ".hook-blocks.log")
            paths.append(root / ".coding-os" / ".hooks.log")
    return paths


def _mine_hook_block_lessons(
    conn: sqlite3.Connection,
    *,
    min_occurrences: int = 3,
    distill_state: dict | None = None,
) -> list[dict]:
    # Hook BLOCKs never reach the observations table on Claude (no PostToolUseFailure)
    # but are in the append-only hook log — mine them there. Fire-and-forget.
    floor = max(1, min(min_occurrences, _FRICTION_MIN_OCCURRENCES))
    # Single source, not a merge: every block is mirrored to both logs, so the
    # block-only log is a strict superset of the main log's surviving blocks.
    # Read the first existing, non-empty candidate (block log preferred) — this
    # avoids double-counting a mirrored block while preserving genuine repeats.
    log_path = None
    for lp in _hook_log_paths(conn):
        try:
            if lp.exists() and lp.stat().st_size > 0:
                log_path = lp
                break
        except OSError:
            continue
    if log_path is None:
        return []
    try:
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        logger.debug("hook-block mining skipped (read %s): %s", log_path, exc)
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=_LESSON_WINDOW_DAYS)
    clusters: dict[str, dict] = {}
    for line in lines:
        match = _BLOCK_LINE_RE.match(line)
        if not match:
            continue
        try:
            ts = datetime.fromisoformat(match.group("ts").replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if ts < cutoff:
                continue
        except ValueError:
            continue  # unparseable timestamp — skip, don't guess
        hook = match.group("hook").strip()
        rest = match.group("rest") or ""
        rule_match = _BLOCK_RULE_RE.search(rest)
        rule = rule_match.group(1) if rule_match else ""
        key = f"{hook}:{rule}"
        cluster = clusters.setdefault(
            key, {"count": 0, "hook": hook, "rule": rule, "samples": []}
        )
        cluster["count"] += 1
        if rest and len(cluster["samples"]) < 3:
            cluster["samples"].append(rest)

    lessons: list[dict] = []
    for key, cluster in clusters.items():
        if cluster["count"] < floor:
            continue
        subject = f"{cluster['hook']} — {cluster['rule']}" if cluster["rule"] else cluster["hook"]
        pattern_text = (
            f"Recurring block ({cluster['count']} occurrences): {subject} "
            f"→ satisfy the blocked rule before retrying the action"
        )
        lessons.append(
            _mint_friction_lesson(
                conn,
                kind="hook_block",
                cluster_key=key,
                count=cluster["count"],
                template_text=pattern_text,
                hook=cluster["hook"],
                rule=cluster["rule"],
                samples=cluster["samples"],
                distill_state=distill_state,
                concepts=json.dumps(["lesson", "hook_block", cluster["hook"]]),
            )
        )
    return lessons


# ---------------------------------------------------------------------------
# Commit-history lesson mining (the real engineering-lesson signal)
# ---------------------------------------------------------------------------

# A Conventional-Commit subject whose type means "something was wrong → fixed":
# fix:/revert: (optional scope, optional !). The subject IS a recorded lesson.
_FIX_COMMIT_RE = re.compile(
    r"^(?P<type>fix|revert)(?:\([^)]*\))?!?:\s*(?P<subject>.+)$", re.IGNORECASE
)

# A one-off `fix:` subject is terse shorthand with no reusable rule — noise.
# Only a fix that RECURS this many times is a systemic-gap signal. Reverts are
# minted at any count (a revert is itself a recorded mistake). See §5 of the doc.
_COMMIT_FIX_MIN_RECURRENCE = 3


def _commit_subject_key(subject: str) -> str:
    s = _TASKID_RE.sub("TASK-N", subject)
    s = _LONGHEX_RE.sub("<hash>", s)
    s = re.sub(r"\d+", "N", s.lower())
    words = [w for w in _NONWORD_RE.split(s) if w]
    return " ".join(words[:8])


def _mine_commit_lessons(conn: sqlite3.Connection, *, min_occurrences: int = 3) -> list[dict]:
    # A fix:/revert: commit IS a recorded "something was wrong → correction".
    # Read-only git log, bounded, no-op outside a work-tree.
    # Contract: docs/engineering/learning-extraction.md §5.
    import subprocess

    root = _derive_project_root(conn)
    if root is None:
        return []
    try:
        proc = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "log",
                f"--since={_LESSON_WINDOW_DAYS} days ago",
                "--max-count=2000",
                "--no-merges",
                "--pretty=format:%s",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.debug("commit mining skipped: %s", exc)
        return []
    if proc.returncode != 0:
        return []

    clusters: dict[str, dict] = {}
    for line in proc.stdout.splitlines():
        match = _FIX_COMMIT_RE.match(line.strip())
        if not match:
            continue
        subject = match.group("subject").strip()
        key = _commit_subject_key(subject)
        if not key:
            continue
        cluster = clusters.setdefault(key, {"count": 0, "subject": subject, "revert": False})
        cluster["count"] += 1
        if match.group("type").lower() == "revert":
            cluster["revert"] = True

    lessons: list[dict] = []
    for cluster in clusters.values():
        is_revert = cluster["revert"]
        subject = _clean_failure_text(cluster["subject"])
        if is_revert:
            # A revert is a recorded "we shipped this and undid it" — real signal.
            pattern_text = (
                f"Reverted before: {subject} → reconsider before re-introducing this change."
            )
        elif cluster["count"] >= _COMMIT_FIX_MIN_RECURRENCE:
            # The RECURRENCE is the signal (same thing keeps breaking), not the
            # subject itself. "(N occurrences)" so _pattern_identity dedups it.
            pattern_text = (
                f"Fixed repeatedly ({cluster['count']} occurrences): {subject} "
                f"→ address the root cause, not the symptom."
            )
        else:
            continue  # one-off / 2x fix subject — no reusable lesson, drop it
        lessons.append(
            _upsert_pattern(
                conn,
                pattern=pattern_text,
                memory_type="lesson",
                domain=None,
                source="commit",
                confidence=min(0.85, 0.4 + cluster["count"] / 10.0),
                concepts=json.dumps(["lesson", "commit", "revert" if is_revert else "fix"]),
            )
        )
    return lessons


# ---------------------------------------------------------------------------
# cos_learn_suggest
# ---------------------------------------------------------------------------


def learn_suggest(
    conn: sqlite3.Connection,
    *,
    domain: str | None = None,
    complexity: str | None = None,
    task_type: str | None = None,
    limit: int = 5,
) -> dict:
    """Return relevant patterns for the current task context.

    Includes spaced repetition: patterns at 0.2-0.4 confidence that
    were once validated get priority with "fading" label.

    Args:
        conn: SQLite connection.
        domain: Task domain (e.g. "BACKEND").
        complexity: Cynefin classification.
        task_type: Type of task (e.g. "feat", "fix").
        limit: Max suggestions (1-20, default 5).

    Returns:
        Dict with suggestions list.
    """
    limit = max(1, min(20, limit))
    suggestions: list[dict] = []

    # --- Active patterns (confidence > 0.3) ---
    # Exclude stats — a success-rate baseline is observability, never a
    # suggestion to act on. See docs/engineering/learning-extraction.md.
    conditions = [
        "confidence >= 0.3",
        "COALESCE(memory_type, '') != 'stat'",
        "promoted_to IS NULL",
    ]
    params: list = []
    if domain:
        conditions.append("(domain = ? OR domain IS NULL)")
        params.append(domain)
    where = " AND ".join(conditions)

    # Relevance boost: complexity + task_type used to be accepted
    # then ignored, so recall was relevance-blind. There is no per-pattern
    # complexity/task_type column, so we BOOST (never exclude) patterns whose
    # concepts/pattern text mention the term — a matching pattern outranks an
    # equally-confident non-match. Boost params bind first (SELECT precedes WHERE).
    boost_terms: list[str] = []
    boost_params: list = []
    for term in (complexity, task_type):
        if term:
            boost_terms.append(
                "(CASE WHEN LOWER(COALESCE(concepts,'')) LIKE ? "
                "OR LOWER(pattern) LIKE ? THEN 1 ELSE 0 END)"
            )
            like = f"%{term.lower()}%"
            boost_params += [like, like]
    relevance = " + ".join(boost_terms) if boost_terms else "0"

    active_rows = conn.execute(
        f"SELECT id, pattern, memory_type, domain, confidence, impact_score, "
        f"times_validated, times_violated, ({relevance}) AS relevance "
        f"FROM learned_patterns WHERE {where} "
        "ORDER BY relevance DESC, confidence DESC, impact_score DESC LIMIT ?",
        boost_params + params + [limit],
    ).fetchall()

    for row in active_rows:
        d = dict(row)
        suggestions.append(
            {
                "id": d["id"],
                "pattern": d["pattern"],
                "confidence": d["confidence"],
                "impact_score": d.get("impact_score", 0.5),
                "memory_type": d["memory_type"],
                "reason": "active",
            }
        )

    # --- Fading patterns (spaced repetition) ---
    fading_conditions = [
        "confidence BETWEEN 0.2 AND 0.4",
        "times_validated >= 1",
        "COALESCE(memory_type, '') != 'stat'",
        "promoted_to IS NULL",
    ]
    fading_params: list = []
    if domain:
        fading_conditions.append("(domain = ? OR domain IS NULL)")
        fading_params.append(domain)
    fading_where = " AND ".join(fading_conditions)

    fading_rows = conn.execute(
        f"SELECT id, pattern, memory_type, domain, confidence, impact_score, "
        f"times_validated, times_violated "
        f"FROM learned_patterns WHERE {fading_where} "
        "ORDER BY confidence ASC LIMIT 3",
        fading_params,
    ).fetchall()

    for row in fading_rows:
        d = dict(row)
        suggestions.insert(
            0,
            {  # fading patterns go first
                "id": d["id"],
                "pattern": d["pattern"],
                "confidence": d["confidence"],
                "impact_score": d.get("impact_score", 0.5),
                "memory_type": d["memory_type"],
                "reason": "fading",
            },
        )

    # --- Breakthrough narratives (high-value lessons from past struggles) ---
    try:
        bt_conditions = ["oh.is_breakthrough = 1", "oh.narrative_key_insight IS NOT NULL"]
        bt_params: list = []
        if domain:
            bt_conditions.append("t.domain = ?")
            bt_params.append(domain)
        bt_where = " AND ".join(bt_conditions)

        bt_rows = conn.execute(
            f"SELECT oh.task_id, oh.narrative_key_insight, oh.narrative_what_failed, "
            f"oh.previous_outcome, t.domain "
            f"FROM outcome_history oh "
            f"LEFT JOIN task_outcomes t ON oh.task_id = t.task_id "
            f"WHERE {bt_where} "
            "ORDER BY oh.created_at DESC LIMIT 3",
            bt_params,
        ).fetchall()

        for row in bt_rows:
            d = dict(row)
            insight = d["narrative_key_insight"] or ""
            failed = d.get("narrative_what_failed") or ""
            label = f"[Breakthrough] {insight}"
            if failed:
                label += f" (avoid: {failed[:60]})"
            suggestions.append(
                {
                    "id": None,
                    "pattern": label,
                    "confidence": 0.8,
                    "impact_score": 0.9,
                    "memory_type": "breakthrough",
                    "reason": f"breakthrough from {d['task_id']}",
                }
            )
    except Exception:
        pass  # outcome_history may not exist on pre-v4 DBs

    return {"suggestions": suggestions[:limit], "count": min(len(suggestions), limit)}


# ---------------------------------------------------------------------------
# cos_learn_validate
# ---------------------------------------------------------------------------


def learn_validate(
    conn: sqlite3.Connection,
    *,
    pattern_id: int,
    was_helpful: bool,
) -> dict:
    """Record whether a suggested pattern was helpful.

    Applies confidence formulas:
      - helpful: LTP with diminishing returns + temporal proximity check
      - not helpful: LTD proportional penalty

    Self-validation throttle:
      - Every call is logged to `pattern_validations` (INSERT, append-only).
      - If the same (session_id, pattern_id, was_helpful=True) was already
        recorded within THROTTLE_WINDOW_SECONDS, the call is marked
        `was_throttled=1` and confidence is NOT boosted. Violation (negative
        feedback) is never throttled — agents must always be able to flag
        bad patterns.

    Args:
        conn: SQLite connection.
        pattern_id: ID in learned_patterns table.
        was_helpful: Whether the pattern was useful.

    Returns:
        Dict with updated confidence and status.
    """
    row = conn.execute(
        "SELECT id, confidence, times_validated, times_violated, decay_rate, trust_tier "
        "FROM learned_patterns WHERE id = ?",
        (pattern_id,),
    ).fetchone()

    if row is None:
        return {"error": f"Pattern not found: id={pattern_id}"}

    # guard: locked/core patterns cannot be mutated via this path
    # even though the trigger would also block it. Return a clean validation
    # error instead of letting SQLite raise.
    trust_tier = row["trust_tier"] if "trust_tier" in row.keys() else "volatile"
    if trust_tier in {"locked", "core"}:
        return {
            "error": f"Pattern {pattern_id} is {trust_tier} — immutable via cos_learn_validate",
            "pattern_id": pattern_id,
            "trust_tier": trust_tier,
        }

    # throttle — only applies to positive validations
    throttled = False
    session_id = _read_session_id_for_validate()
    if was_helpful and _has_recent_validation(conn, session_id, pattern_id):
        throttled = True

    # Always log the attempt (throttled or not) for audit + sycophancy
    # detection in later phases.
    _log_validation(
        conn,
        session_id=session_id,
        pattern_id=pattern_id,
        was_helpful=was_helpful,
        was_throttled=throttled,
    )

    if throttled:
        # Return current state without confidence mutation
        return {
            "status": "throttled",
            "pattern_id": pattern_id,
            "old_confidence": round(row["confidence"], 4),
            "new_confidence": round(row["confidence"], 4),
            "was_helpful": was_helpful,
            "reason": f"same (session, pattern) validated within {_THROTTLE_WINDOW_SECONDS}s",
        }

    old_conf = row["confidence"]
    decay_rate = row["decay_rate"]

    if was_helpful:
        new_conf = boost_success(old_conf)

        # Temporal proximity check — 2+ validations in 48h
        recent_count = conn.execute(
            "SELECT COUNT(*) FROM learned_patterns "
            "WHERE id = ? AND last_validated >= datetime('now', '-48 hours')",
            (pattern_id,),
        ).fetchone()[0]

        if recent_count >= 1:  # this will be the 2nd+ in 48h
            new_conf = min(0.95, new_conf + 0.05)
            decay_rate = decay_rate * 0.7

        conn.execute(
            "UPDATE learned_patterns SET "
            "confidence = ?, "
            "times_validated = times_validated + 1, "
            "last_validated = CURRENT_TIMESTAMP, "
            "decay_rate = ? "
            "WHERE id = ?",
            (new_conf, decay_rate, pattern_id),
        )
    else:
        new_conf = penalize_failure(old_conf)
        conn.execute(
            "UPDATE learned_patterns SET "
            "confidence = ?, "
            "times_violated = times_violated + 1, "
            "last_validated = CURRENT_TIMESTAMP "
            "WHERE id = ?",
            (new_conf, pattern_id),
        )

    conn.commit()
    return {
        "status": "validated" if was_helpful else "penalized",
        "pattern_id": pattern_id,
        "old_confidence": round(old_conf, 4),
        "new_confidence": round(new_conf, 4),
        "was_helpful": was_helpful,
    }


# ---------------------------------------------------------------------------
# Breakthrough narrative capture
# ---------------------------------------------------------------------------


_GENERIC_INSIGHT_RE = re.compile(
    r"\b(be careful|be more careful|double[- ]check|pay attention|take care|"
    r"more thorough|review carefully|test more|don'?t forget)\b",
    re.IGNORECASE,
)


def _is_low_quality_insight(text: str) -> bool:
    # Reject ultra-terse / generic "be careful" slop with no transferable rule;
    # specific-but-short insights like "Money must use Decimal" still pass.
    t = (text or "").strip()
    if len(t) < 8:
        return True
    return bool(_GENERIC_INSIGHT_RE.search(t))


def learn_narrative(
    conn: sqlite3.Connection,
    *,
    task_id: str,
    what_failed: str = "",
    what_worked: str = "",
    key_insight: str = "",
) -> dict:
    """Record a breakthrough narrative and create a high-impact learned pattern.

    Called by the agent after a rework→success breakthrough. Updates the
    outcome_history narrative fields and creates a learned_pattern with
    memory_type='error' and high confidence.

    Args:
        conn: SQLite connection.
        task_id: Task identifier (e.g. "TASK-100").
        what_failed: Approaches that didn't work.
        what_worked: The solution that resolved the issue.
        key_insight: Reusable lesson learned.

    Returns:
        Dict with status, history_id, pattern_id.
    """
    if not task_id:
        return {"error": "task_id is required"}
    if not key_insight:
        return {"error": "key_insight is required — what did you learn?"}

    # sanitize all narrative fields before they enter memory.
    # Reject on injection patterns; truncate over-length text.
    # Single-pass: compute cleaned values once so audit log records each
    # truncation/reject exactly once.
    from sanitizer import sanitize_write

    _sanitized: dict[str, str] = {}
    for _field, _value in (
        ("key_insight", key_insight),
        ("what_failed", what_failed),
        ("what_worked", what_worked),
    ):
        _sr = sanitize_write(
            _field,
            _value,
            actor="learn_narrative",
            source_table="outcome_history",
            conn=conn,
        )
        if not _sr.ok:
            return {"error": f"rejected {_field}: {_sr.reason}"}
        _sanitized[_field] = _sr.cleaned or ""

    key_insight = _sanitized["key_insight"]
    what_failed = _sanitized["what_failed"]
    what_worked = _sanitized["what_worked"]

    # Quality bar: a narrative is only worth storing if the insight is specific.
    # Blocks "be careful"-class slop the nudge could otherwise elicit.
    if _is_low_quality_insight(key_insight):
        return {
            "error": "key_insight too generic — state the specific situation, why the "
            "naive approach failed, and the rule to apply (not 'be careful')."
        }

    # Find the most recent breakthrough for this task
    row = conn.execute(
        "SELECT id, outcome, previous_outcome FROM outcome_history "
        "WHERE task_id = ? AND is_breakthrough = 1 "
        "ORDER BY created_at DESC LIMIT 1",
        (task_id,),
    ).fetchone()

    if row is None:
        # No breakthrough found — create a general narrative entry anyway
        cursor = conn.execute(
            "INSERT INTO outcome_history "
            "(task_id, outcome, previous_outcome, is_breakthrough, "
            "narrative_what_failed, narrative_what_worked, narrative_key_insight, triggered_by) "
            "VALUES (?, 'success', NULL, 0, ?, ?, ?, 'learn_narrative')",
            (task_id, what_failed, what_worked, key_insight),
        )
        history_id = cursor.lastrowid
    else:
        history_id = row["id"]
        conn.execute(
            "UPDATE outcome_history SET "
            "narrative_what_failed = ?, narrative_what_worked = ?, narrative_key_insight = ? "
            "WHERE id = ?",
            (what_failed, what_worked, key_insight, history_id),
        )

    # Get task domain for the pattern
    task_row = conn.execute(
        "SELECT domain, complexity FROM task_outcomes WHERE task_id = ?", (task_id,)
    ).fetchone()
    domain = task_row["domain"] if task_row else None

    # Build concepts from narrative text
    words = set()
    for text in (what_failed, what_worked, key_insight):
        words.update(w.lower() for w in text.split() if len(w) > 3)
    # Keep only meaningful concept words (no stop words)
    stop = {"that", "this", "with", "from", "have", "been", "were", "will", "didn't", "wasn't"}
    concept_list = sorted(words - stop)[:7]
    if domain:
        concept_list.insert(0, domain.lower())

    # Create a high-impact learned pattern
    pattern_text = f"[Breakthrough] {key_insight}"
    if what_failed:
        pattern_text += f" (failed: {what_failed[:80]})"

    # evidence-based auto-promote.
    # Previously this inserted with confidence=0.7 / impact=0.85 /
    # no provenance, letting the agent self-certify a "breakthrough"
    # at high trust after a single call (audit finding A7). Now the
    # row is explicitly volatile/agent_self at moderate confidence;
    # promotion to `validated` requires external evidence (outcome
    # history or explicit `cos_promote`), handled elsewhere.
    cursor = conn.execute(
        "INSERT INTO learned_patterns "
        "(pattern, memory_type, domain, source, confidence, impact_score, "
        "concepts, trust_tier, provenance) "
        "VALUES (?, 'error', ?, 'breakthrough', 0.3, 0.5, ?, "
        "'volatile', 'agent_self')",
        (pattern_text, domain, json.dumps(concept_list)),
    )
    pattern_id = cursor.lastrowid

    conn.commit()

    # RAG: embed both the breakthrough narrative (outcome_history)
    # and the high-impact learned pattern. Errors are intentionally suppressed
    # because embeddings are an optional enrichment — never fail the narrative
    # recording itself if rag extras are not installed or v5 not yet applied.
    _embed_narrative_and_pattern(
        conn=conn,
        history_id=history_id,
        pattern_id=pattern_id,
        pattern_text=pattern_text,
        concept_list=concept_list,
        key_insight=key_insight,
        what_failed=what_failed,
        what_worked=what_worked,
    )

    # Filing-back: write a human-readable markdown file to docs/insights/.
    # Fire-and-forget — filing failure must never break narrative recording.
    filed_path = _file_back_narrative_safe(
        conn=conn,
        task_id=task_id,
        domain=domain,
        key_insight=key_insight,
        what_failed=what_failed,
        what_worked=what_worked,
        history_id=history_id,
        pattern_id=pattern_id,
    )

    return {
        "status": "narrative_recorded",
        "history_id": history_id,
        "pattern_id": pattern_id,
        "task_id": task_id,
        "domain": domain,
        "filed_path": str(filed_path) if filed_path else None,
    }


def _embed_narrative_and_pattern(
    *,
    conn: sqlite3.Connection,
    history_id: int,
    pattern_id: int,
    pattern_text: str,
    concept_list: list,
    key_insight: str,
    what_failed: str,
    what_worked: str,
) -> None:
    # Fire-and-forget: embeddings are optional enrichment — never fail the
    # narrative recording (missing module/table/model load all swallowed).
    try:
        from embeddings import upsert_embedding
    except ImportError as exc:
        logger.debug("Skipping embedding (module unavailable): %s", exc)
        return

    try:
        narrative_text = " ".join(filter(None, [key_insight, what_failed, what_worked]))
        upsert_embedding(conn, "outcome_history", history_id, narrative_text)
        pattern_concepts_str = " ".join(concept_list)
        upsert_embedding(
            conn,
            "learned_patterns",
            pattern_id,
            f"{pattern_text} {pattern_concepts_str}".strip(),
        )
    except sqlite3.OperationalError as exc:
        logger.debug("Skipping embedding (table missing — pre-v5 DB): %s", exc)
    except Exception as exc:  # pragma: no cover - defensive against model load errors
        logger.debug("Skipping embedding (unexpected): %s", exc)


# ---------------------------------------------------------------------------
# Breakthrough narrative filing-back (human-readable markdown artifact)
# ---------------------------------------------------------------------------

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(text: str, max_len: int = 50) -> str:
    slug = _SLUG_RE.sub("-", text.lower()).strip("-")
    if not slug:
        return "untitled"
    return slug[:max_len].rstrip("-") or "untitled"


def _derive_project_root(conn: sqlite3.Connection) -> Path | None:
    # Root = parent of the .coding-os/ dir holding the DB. None for in-memory
    # DBs or any DB outside the expected <root>/.coding-os/coding-os.db layout.
    rows = conn.execute("PRAGMA database_list").fetchall()
    for row in rows:
        db_path_str = row[2] if len(row) > 2 else None
        if not db_path_str:
            continue
        if db_path_str in ("", ":memory:"):
            continue
        db_path = Path(db_path_str).resolve()
        if db_path.parent.name == ".coding-os":
            return db_path.parent.parent
    return None


def _format_narrative_markdown(
    *,
    task_id: str,
    domain: str | None,
    key_insight: str,
    what_failed: str,
    what_worked: str,
    history_id: int,
    pattern_id: int,
) -> str:
    date_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    domain_line = domain or "n/a"
    failed_block = what_failed.strip() or "_(not recorded)_"
    worked_block = what_worked.strip() or "_(not recorded)_"
    return (
        f"<!-- domain:{domain_line} | layer:reference | ssot:false | "
        f"source:outcome_history#{history_id} | updated:{date_iso} -->\n"
        f"# {task_id}: {key_insight}\n\n"
        f"**Date:** {date_iso}  \n"
        f"**Domain:** {domain_line}  \n"
        f"**Source task:** [{task_id}](../tasks/{task_id}.md)\n\n"
        f"## Key Insight\n\n{key_insight}\n\n"
        f"## What Failed\n\n{failed_block}\n\n"
        f"## What Worked\n\n{worked_block}\n\n"
        f"## Links\n\n"
        f"- Pattern: `learned_patterns#{pattern_id}` — retrievable via `cos_details`\n"
        f"- History: `outcome_history#{history_id}`\n"
    )


def _file_back_narrative_safe(
    *,
    conn: sqlite3.Connection,
    task_id: str,
    domain: str | None,
    key_insight: str,
    what_failed: str,
    what_worked: str,
    history_id: int,
    pattern_id: int,
) -> Path | None:
    # Fire-and-forget write to <root>/docs/insights/; returns None (skipped)
    # for in-memory DBs or when <root>/docs/ is absent. Never breaks recording.
    try:
        project_root = _derive_project_root(conn)
        if project_root is None:
            logger.debug("Skipping narrative filing (project root not derivable)")
            return None
        docs_root = project_root / "docs"
        if not docs_root.exists():
            logger.debug("Skipping narrative filing (no docs/ at %s)", project_root)
            return None

        target_dir = docs_root / "insights"
        target_dir.mkdir(parents=True, exist_ok=True)

        slug = _slugify(f"{task_id}-{key_insight}")
        target_path = target_dir / f"{slug}.md"
        content = _format_narrative_markdown(
            task_id=task_id,
            domain=domain,
            key_insight=key_insight,
            what_failed=what_failed,
            what_worked=what_worked,
            history_id=history_id,
            pattern_id=pattern_id,
        )
        target_path.write_text(content, encoding="utf-8")
        return target_path
    except OSError as exc:
        logger.debug("Skipping narrative filing (OS error): %s", exc)
        return None
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("Skipping narrative filing (unexpected): %s", exc)
        return None
