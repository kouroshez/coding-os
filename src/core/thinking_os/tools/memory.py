"""
Thinking OS — MCP memory tools (TASK-142).

4 tools for tiered memory access:
  - thinking_os_search:   index-level results (~50 tokens)
  - thinking_os_timeline: recent activity (~150 tokens)
  - thinking_os_details:  full record (~500 tokens)
  - thinking_os_promote:  pattern → rule/feedback file

Module layout:
  _memory_ranking   5-signal score, RRF fusion, MMR diversity, access boost
  _memory_semantic  vector recall + row hydration for semantic hits
  _memory_search    the cos_search retrieval pass those two feed
  this module       timeline, details, and promote
"""

from __future__ import annotations

import logging
import sqlite3

from ._memory_ranking import (
    MMR_LAMBDA as MMR_LAMBDA,
    RRF_K as RRF_K,
    W_ACCESS as W_ACCESS,
    W_CONFIDENCE as W_CONFIDENCE,
    W_IMPACT as W_IMPACT,
    W_RECENCY as W_RECENCY,
    W_RELEVANCE as W_RELEVANCE,
    _access_score as _access_score,
    _boost_access,
    _compute_score as _compute_score,
    _days_since as _days_since,
    _fts5_safe_query as _fts5_safe_query,
    _jaccard as _jaccard,
    _mmr_select as _mmr_select,
    _re_verify_recommended as _re_verify_recommended,
    _recency_score as _recency_score,
    _rrf_fuse as _rrf_fuse,
    _tokenize as _tokenize,
)
from ._memory_search import (
    VALID_MEMORY_TYPES as VALID_MEMORY_TYPES,
    memory_search as memory_search,
)
from ._memory_semantic import (
    _augment_with_semantic as _augment_with_semantic,
    _hydrate_row_for_semantic_hit as _hydrate_row_for_semantic_hit,
)

logger = logging.getLogger("thinking_os.memory")

VALID_SOURCES = {"observations", "learned_patterns", "task_outcomes"}
VALID_PROMOTE_TARGETS = {"feedback", "rule"}


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
        [*params, limit],
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
    obs_conditions.append("COALESCE(memory_type, '') != 'changelog'")
    obs_where = " AND ".join(obs_conditions)

    obs_rows = conn.execute(
        f"SELECT id, title, memory_type, created_at "
        f"FROM observations WHERE {obs_where} "
        "ORDER BY created_at DESC LIMIT ?",
        [*obs_params, limit],
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
