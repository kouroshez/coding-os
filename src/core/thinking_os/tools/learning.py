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
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("thinking_os.learning")

# Dual import identity (flat `tools.learning` vs package `thinking_os.tools.learning`)
# — try the package form, fall back to the bare one.
try:  # package import
    from ._learning_mining import (
        _clean_failure_text,
        _failure_cluster_key,
        _friction_kind,
        _mine_friction_lessons,
        _mint_friction_lesson,
        _normalize_full,
    )
    from ._learning_mining_logs import (
        _commit_subject_key,
        _mine_commit_lessons,
        _mine_hook_block_lessons,
    )
    from ._learning_narrative import (
        _file_back_narrative_safe,
        _is_low_quality_insight,
        learn_narrative,
    )
    from ._learning_store import (
        _adopt_legacy_template,
        _derive_project_root,
        _distill_fingerprint_safe,
        _distill_safe,
        _embed_pattern_safe,
        _pattern_identity,
        _upsert_pattern,
        pattern_tier,
    )
except ImportError:  # flat import
    from _learning_mining import (  # type: ignore[no-redef]  # noqa: F401
        _clean_failure_text,
        _failure_cluster_key,
        _friction_kind,
        _mine_friction_lessons,
        _mint_friction_lesson,
        _normalize_full,
    )
    from _learning_mining_logs import (  # type: ignore[no-redef]  # noqa: F401
        _commit_subject_key,
        _mine_commit_lessons,
        _mine_hook_block_lessons,
    )
    from _learning_narrative import (  # type: ignore[no-redef]  # noqa: F401
        _file_back_narrative_safe,
        _is_low_quality_insight,
        learn_narrative,
    )
    from _learning_store import (  # type: ignore[no-redef]  # noqa: F401
        _adopt_legacy_template,
        _derive_project_root,
        _distill_fingerprint_safe,
        _distill_safe,
        _embed_pattern_safe,
        _pattern_identity,
        _upsert_pattern,
        pattern_tier,
    )


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
        _mine_friction_lessons(conn, min_occurrences=min_occurrences, distill_state=distill_state)
    )
    # Hook BLOCKs live in the activity log (not observations) on Claude — mine
    # them too so the richest friction signal becomes a lesson.
    extracted.extend(
        _mine_hook_block_lessons(conn, min_occurrences=min_occurrences, distill_state=distill_state)
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


# ---------------------------------------------------------------------------
# Friction lesson mining (the real learning signal)
# ---------------------------------------------------------------------------

# A friction event seen this many times is already worth a rule. Lower than the


def _load_surfaced_suggestions(path: Path) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if "\t" not in line:
            continue
        pid_s, text = line.split("\t", 1)
        try:
            out.append((int(pid_s), text))
        except ValueError:
            continue
    return out


# ---------------------------------------------------------------------------
# Commit-history lesson mining (the real engineering-lesson signal)
# ---------------------------------------------------------------------------


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
        # Established-ness (occurrence), not validation: after the honest
        # times_validated reset a "seen" pattern still resurfaces for review.
        "times_seen >= 1",
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
    # sqlite3.Row has no .get(), and bare `in row` scans VALUES — keys() is required.
    trust_tier = row["trust_tier"] if "trust_tier" in row.keys() else "volatile"  # noqa: SIM118
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


def validate_surfaced_lessons(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    suggestions_path: str | Path,
) -> dict:
    """Close the learn->apply->confirm loop for one completed task: validate each
    lesson surfaced during Orient against this session's post-recall friction — a
    lesson whose failure recurred is penalized (LTD), the rest reinforced (LTP).

    The single primitive BOTH the task-done Bash hook and the MCP completion path
    call; divergence here was why surfaced patterns never reached the Trusted tier.
    """
    sf = Path(suggestions_path)
    if not session_id or not sf.exists():
        return {"status": "skipped"}
    surfaced = _load_surfaced_suggestions(sf)
    if not surfaced:
        return {"status": "no_suggestions"}

    # Only failures recorded AT/AFTER the recall (suggestions file mtime) count.
    recall_at = datetime.fromtimestamp(sf.stat().st_mtime, tz=timezone.utc).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    rows = conn.execute(
        "SELECT narrative, title, memory_type FROM observations "
        "WHERE session_id = ? AND memory_type IN ('hook_block', 'error') "
        "  AND created_at >= ?",
        (session_id, recall_at),
    ).fetchall()
    failure_keys: list[str] = []
    failure_fingerprints: set[str] = set()
    for r in rows:
        d = dict(r)
        key = _failure_cluster_key(_clean_failure_text(d["narrative"] or d["title"] or ""))
        if not key:
            continue
        failure_keys.append(key)
        fp = _distill_fingerprint_safe(
            _friction_kind(d["title"], d["narrative"], d["memory_type"]), key
        )
        if fp:
            failure_fingerprints.add(fp)

    # A distilled lesson no longer contains the raw failure text, so matching its
    # display text alone would always read helpful=True. Match the stored
    # fingerprint and evidence samples too.
    lesson_meta: dict[int, tuple[str, str]] = {}
    try:
        placeholders = ",".join("?" * len(surfaced))
        for row in conn.execute(
            "SELECT id, distill_fingerprint, evidence_json FROM learned_patterns "
            f"WHERE id IN ({placeholders})",
            [pid for pid, _ in surfaced],
        ):
            d = dict(row)
            lesson_meta[d["id"]] = (
                d.get("distill_fingerprint") or "",
                _normalize_full(d.get("evidence_json") or ""),
            )
    except sqlite3.Error:
        lesson_meta = {}

    helpful = unhelpful = 0
    for pid, text in surfaced:
        lesson_norm = _normalize_full(text)
        fingerprint, evidence_norm = lesson_meta.get(pid, ("", ""))
        recurred = (fingerprint and fingerprint in failure_fingerprints) or any(
            key in lesson_norm or (evidence_norm and key in evidence_norm) for key in failure_keys
        )
        learn_validate(conn, pattern_id=pid, was_helpful=not recurred)
        if recurred:
            unhelpful += 1
        else:
            helpful += 1
    return {
        "status": "ok",
        "surfaced": len(surfaced),
        "helpful": helpful,
        "unhelpful": unhelpful,
    }


# ---------------------------------------------------------------------------
