"""
Thinking OS — MCP learning tools (TASK-144, TASK-147).

4 tools for pattern mining and rule suggestion:
  - cos_learn_extract: discover patterns from task outcomes
  - cos_learn_suggest: return relevant patterns for current context
  - cos_learn_validate: confirm/deny a pattern's usefulness
  - generate_feedback_drafts: auto-generate feedback files from rework clusters (TASK-147)
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger("thinking_os.learning")

MIN_DATA_THRESHOLD = 3  # minimum task outcomes before extraction

# Phase G.4 — self-validation throttle window. Same (session, pattern)
# positive validation is ignored within this window. 1h is long enough to
# cover a continuous task loop but short enough that legitimate re-use
# across sessions isn't suppressed.
_THROTTLE_WINDOW_SECONDS = 3600


def _read_session_id_for_validate() -> str:
    """Read active session id for throttle bookkeeping."""
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
    """Return True when (session, pattern, was_helpful=1) was logged recently."""
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
    """Append a row to pattern_validations. Fire-and-forget — never raises."""
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
                f"Skill '{d['skills_used']}' correlates with rework "
                f"({d['count']} occurrences)"
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

    # --- Failure anatomy patterns (Phase EVO v25) ---
    # Mine structured backtrack_events for recurring root_cause patterns.
    # Only runs when anatomy columns are present (migration v25).
    try:
        anat_rows = conn.execute(
            "SELECT root_cause, COUNT(*) AS cnt, "
            "       GROUP_CONCAT(DISTINCT from_formula) AS formulas "
            "FROM backtrack_events "
            "WHERE root_cause IS NOT NULL "
            "GROUP BY root_cause "
            "HAVING cnt >= ?",
            (min_occurrences,),
        ).fetchall()
        for row in anat_rows:
            d = dict(row)
            confidence = min(0.85, d["cnt"] / 20.0 + 0.3)
            formulas_str = d["formulas"] or ""
            pattern_text = (
                f"Recurring backtrack root cause '{d['root_cause']}' "
                f"({d['cnt']} occurrences"
                + (f"; formulas: {formulas_str[:60]}" if formulas_str else "")
                + ")"
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

    conn.commit()
    return {
        "status": "ok",
        "total_outcomes_analyzed": total_outcomes,
        "extracted": extracted,
    }


_SOURCE_TO_PROVENANCE: dict[str, str] = {
    "learn_extract": "extracted_from_outcome",
    "breakthrough": "agent_self",
    "manual": "user_directive",
    "import": "imported",
}


def _upsert_pattern(
    conn: sqlite3.Connection,
    *,
    pattern: str,
    memory_type: str,
    domain: Optional[str],
    source: str,
    confidence: float,
    concepts: str,
    provenance: Optional[str] = None,
) -> dict:
    """Insert a new pattern or update existing one's confidence.

    Phase G.2: runs the sanitizer on `pattern` before any DB write. A rejected
    pattern returns `{"action": "rejected", ...}` and no row is created or
    updated. Truncation is applied transparently (over-cap text is shortened,
    operation proceeds).

    Phase G.6: stamps `provenance` on every new row (derived from `source`
    when not supplied). Keeps agent_self writes distinguishable from mined
    data for later sycophancy analysis.
    """
    if provenance is None:
        provenance = _SOURCE_TO_PROVENANCE.get(source, "agent_self")
    from sanitizer import sanitize_write

    p_sr = sanitize_write(
        "pattern", pattern,
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

    existing = conn.execute(
        "SELECT id, confidence, times_validated FROM learned_patterns "
        "WHERE pattern = ? AND domain IS ?",
        (pattern, domain),
    ).fetchone()

    if existing:
        # Update confidence (take the higher)
        new_conf = max(existing["confidence"], confidence)
        conn.execute(
            "UPDATE learned_patterns SET confidence = ?, last_validated = CURRENT_TIMESTAMP "
            "WHERE id = ?",
            (new_conf, existing["id"]),
        )
        pattern_id = existing["id"]
        result = {"id": pattern_id, "pattern": pattern, "confidence": new_conf, "action": "updated"}
    else:
        cursor = conn.execute(
            "INSERT INTO learned_patterns "
            "(pattern, memory_type, domain, source, confidence, concepts, provenance) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (pattern, memory_type, domain, source, confidence, concepts, provenance),
        )
        pattern_id = cursor.lastrowid
        result = {"id": pattern_id, "pattern": pattern, "confidence": confidence, "action": "created"}

    # Phase B RAG: embed the pattern for semantic search.
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
    """Embed a learned pattern row. Errors logged at debug level only."""
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
# cos_learn_suggest
# ---------------------------------------------------------------------------

def learn_suggest(
    conn: sqlite3.Connection,
    *,
    domain: Optional[str] = None,
    complexity: Optional[str] = None,
    task_type: Optional[str] = None,
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
    conditions = ["confidence >= 0.3"]
    params: list = []
    if domain:
        conditions.append("(domain = ? OR domain IS NULL)")
        params.append(domain)
    where = " AND ".join(conditions)

    active_rows = conn.execute(
        f"SELECT id, pattern, memory_type, domain, confidence, impact_score, "  # noqa: S608
        f"times_validated, times_violated "
        f"FROM learned_patterns WHERE {where} "
        "ORDER BY confidence DESC, impact_score DESC LIMIT ?",
        params + [limit],
    ).fetchall()

    for row in active_rows:
        d = dict(row)
        suggestions.append({
            "id": d["id"],
            "pattern": d["pattern"],
            "confidence": d["confidence"],
            "impact_score": d.get("impact_score", 0.5),
            "memory_type": d["memory_type"],
            "reason": "active",
        })

    # --- Fading patterns (spaced repetition) ---
    fading_conditions = [
        "confidence BETWEEN 0.2 AND 0.4",
        "times_validated >= 1",
    ]
    fading_params: list = []
    if domain:
        fading_conditions.append("(domain = ? OR domain IS NULL)")
        fading_params.append(domain)
    fading_where = " AND ".join(fading_conditions)

    fading_rows = conn.execute(
        f"SELECT id, pattern, memory_type, domain, confidence, impact_score, "  # noqa: S608
        f"times_validated, times_violated "
        f"FROM learned_patterns WHERE {fading_where} "
        "ORDER BY confidence ASC LIMIT 3",
        fading_params,
    ).fetchall()

    for row in fading_rows:
        d = dict(row)
        suggestions.insert(0, {  # fading patterns go first
            "id": d["id"],
            "pattern": d["pattern"],
            "confidence": d["confidence"],
            "impact_score": d.get("impact_score", 0.5),
            "memory_type": d["memory_type"],
            "reason": "fading",
        })

    # --- Breakthrough narratives (high-value lessons from past struggles) ---
    try:
        bt_conditions = ["oh.is_breakthrough = 1", "oh.narrative_key_insight IS NOT NULL"]
        bt_params: list = []
        if domain:
            bt_conditions.append("t.domain = ?")
            bt_params.append(domain)
        bt_where = " AND ".join(bt_conditions)

        bt_rows = conn.execute(
            f"SELECT oh.task_id, oh.narrative_key_insight, oh.narrative_what_failed, "  # noqa: S608
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
            suggestions.append({
                "id": None,
                "pattern": label,
                "confidence": 0.8,
                "impact_score": 0.9,
                "memory_type": "breakthrough",
                "reason": f"breakthrough from {d['task_id']}",
            })
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

    Phase G.4 — Self-validation throttle:
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

    # Phase G.1 guard: locked/core patterns cannot be mutated via this path
    # even though the trigger would also block it. Return a clean validation
    # error instead of letting SQLite raise.
    trust_tier = row["trust_tier"] if "trust_tier" in row.keys() else "volatile"
    if trust_tier in {"locked", "core"}:
        return {
            "error": f"Pattern {pattern_id} is {trust_tier} — immutable via cos_learn_validate",
            "pattern_id": pattern_id,
            "trust_tier": trust_tier,
        }

    # Phase G.4 throttle — only applies to positive validations
    throttled = False
    session_id = _read_session_id_for_validate()
    if was_helpful and _has_recent_validation(conn, session_id, pattern_id):
        throttled = True

    # Always log the attempt (throttled or not) for audit + sycophancy
    # detection in later phases.
    _log_validation(conn, session_id=session_id, pattern_id=pattern_id,
                    was_helpful=was_helpful, was_throttled=throttled)

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
# Auto-feedback generation (TASK-147)
# ---------------------------------------------------------------------------

FEEDBACK_THRESHOLD = 3  # minimum rework tasks to trigger feedback draft


def generate_feedback_drafts(
    conn: sqlite3.Connection,
    *,
    min_rework: int = FEEDBACK_THRESHOLD,
) -> dict:
    """Detect rework clusters and generate draft feedback files.

    Scans task_outcomes for domain+skill combinations with 3+ reworks.
    Returns draft feedback content (does NOT write files — caller handles I/O).

    Args:
        conn: SQLite connection.
        min_rework: Minimum rework tasks to trigger a draft (default 3).

    Returns:
        Dict with drafts list.
    """
    rows = conn.execute(
        "SELECT domain, skills_used, "
        "SUM(CASE WHEN outcome = 'rework' THEN 1 ELSE 0 END) AS rework_count, "
        "COUNT(*) AS total_count, "
        "GROUP_CONCAT(CASE WHEN outcome = 'rework' THEN task_id END, ', ') AS rework_tasks "
        "FROM task_outcomes "
        "WHERE skills_used IS NOT NULL AND skills_used != '' "
        "GROUP BY domain, skills_used "
        "HAVING rework_count >= ?",
        (min_rework,),
    ).fetchall()

    drafts: list[dict] = []

    for row in rows:
        d = dict(row)
        domain = d["domain"] or "UNKNOWN"
        skill = d["skills_used"] or "unknown"
        rework_rate = d["rework_count"] / d["total_count"] if d["total_count"] > 0 else 0

        slug = f"{domain.lower()}_{skill.replace('-', '_')}_rework"
        filename = f"feedback_draft_{slug}.md"

        content = (
            f"---\n"
            f"name: {slug}\n"
            f"description: Auto-detected rework pattern in {domain} with {skill}\n"
            f"type: feedback\n"
            f"status: draft\n"
            f"---\n\n"
            f"{domain} tasks using {skill} have a {rework_rate:.0%} rework rate "
            f"({d['rework_count']}/{d['total_count']} tasks).\n\n"
            f"**Evidence:** {d['rework_tasks']}\n\n"
            f"**Suggested rule:** Review {domain} {skill} tasks more carefully before marking done. "
            f"Consider adding additional verification steps.\n\n"
            f"**Why:** {d['rework_count']} tasks required rework, indicating a systematic gap.\n\n"
            f"**How to apply:** When working on {domain} tasks with {skill}, "
            f"double-check the verification matrix before closing.\n"
        )

        drafts.append({
            "filename": filename,
            "content": content,
            "domain": domain,
            "skill": skill,
            "rework_count": d["rework_count"],
            "total_count": d["total_count"],
            "rework_rate": round(rework_rate, 2),
            "evidence_tasks": d["rework_tasks"],
        })

    return {"drafts": drafts, "count": len(drafts)}


# ---------------------------------------------------------------------------
# Breakthrough narrative capture
# ---------------------------------------------------------------------------

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

    # Phase G.2: sanitize all narrative fields before they enter memory.
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
            _field, _value,
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

    # Phase G.6 — evidence-based auto-promote.
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

    # Phase B RAG: embed both the breakthrough narrative (outcome_history)
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

    # Filing-back: write a human-readable markdown file to docs/breakthroughs/.
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
    """Embed a breakthrough narrative + its derived pattern (Phase B RAG).

    Fire-and-forget: any failure (missing module, missing table, model load
    failure) is logged at debug level and swallowed. Embeddings are an
    optional enrichment — they must never fail the narrative recording.
    """
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


def _derive_project_root(conn: sqlite3.Connection) -> Optional[Path]:
    """Project root = parent of the .coding-os/ directory holding the DB.

    Returns None for in-memory DBs or DBs outside the expected
    <root>/.coding-os/coding-os.db layout.
    """
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
    domain: Optional[str],
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
    domain: Optional[str],
    key_insight: str,
    what_failed: str,
    what_worked: str,
    history_id: int,
    pattern_id: int,
) -> Optional[Path]:
    """Write a markdown narrative to `<root>/docs/breakthroughs/`.

    Fire-and-forget: any failure is logged at debug level and swallowed.
    Skipped silently when:
      - DB is in-memory or not in the expected `<root>/.coding-os/` layout
      - `<root>/docs/` does not exist (not a coding-os project layout)

    Returns the written path, or None if skipped.
    """
    try:
        project_root = _derive_project_root(conn)
        if project_root is None:
            logger.debug("Skipping narrative filing (project root not derivable)")
            return None
        docs_root = project_root / "docs"
        if not docs_root.exists():
            logger.debug("Skipping narrative filing (no docs/ at %s)", project_root)
            return None

        target_dir = docs_root / "breakthroughs"
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
