"""
Coding OS — Agent digest.

Rolling snapshot of what the agent currently "knows" and "prefers",
stored at `<project>/.coding-os/digest.md` and refreshed on demand
(or by the background indexer on a daily cadence).

Why:
    Memory is huge (observations, learned_patterns, outcome_history)
    but most of it is low-signal for a new session. The digest is a
    compact, always-in-context summary that gives the agent an
    identity anchor before any retrieval happens.

Structure (≤ ~2.4KB, hard cap in _RENDER_BUDGET_CHARS):
    # Agent Digest — YYYY-MM-DD
    ## Identity        — task counts, top domains, success rate
    ## Active Beliefs  — top N learned patterns by confidence × impact
    ## Fading          — patterns near decay threshold, due for review
    ## Recent Breakthroughs — key_insight lines from last 7d
    ## Preferences     — workflow/decision patterns

Public API:
    regenerate(conn, *, project_root, now=None) -> dict
    render(conn, *, now=None) -> str
    read_digest_path(project_root) -> Path
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

try:
    from tools.trajectory import trajectory_digest_line as _trajectory_digest_line
except ImportError:

    def _trajectory_digest_line(conn) -> str:  # type: ignore[misc]
        return ""


logger = logging.getLogger("coding_os.digest")

# Hard cap on the rendered markdown. Chosen so the digest fits comfortably
# inside the agent's always-active context alongside AGENTS.md + rules.
_RENDER_BUDGET_CHARS = 2400

# How many items from each section to consider before trimming for budget.
_TOP_BELIEFS = 5
_TOP_FADING = 3
_TOP_BREAKTHROUGHS = 3
_TOP_PREFERENCES = 4
_TOP_STATS = 3

# Confidence windows
_FADING_MIN = 0.2
_FADING_MAX = 0.4
_ACTIVE_MIN = 0.5


def read_digest_path(project_root: Path) -> Path:
    """Return the canonical digest file path under `<root>/.coding-os/`."""
    return project_root.resolve() / ".coding-os" / "digest.md"


def regenerate(
    conn: sqlite3.Connection,
    *,
    project_root: Path,
    now: datetime | None = None,
) -> dict:
    """Render the digest and write it to `.coding-os/digest.md`."""
    body = render(conn, now=now)
    target = read_digest_path(project_root)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")

    return {
        "path": str(target),
        "size_chars": len(body),
        "truncated": "[truncated]" in body,
        "status": "ok",
    }


def render(
    conn: sqlite3.Connection,
    *,
    now: datetime | None = None,
) -> str:
    """Build the digest markdown string and enforce the token budget."""
    now = now or datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")

    identity = _collect_identity(conn)
    trajectory = _trajectory_digest_line(conn)
    beliefs = _collect_beliefs(conn, limit=_TOP_BELIEFS)
    fading = _collect_fading(conn, limit=_TOP_FADING)
    breakthroughs = _collect_breakthroughs(conn, limit=_TOP_BREAKTHROUGHS)
    preferences = _collect_preferences(conn, limit=_TOP_PREFERENCES)
    stats = _collect_stats(conn, limit=_TOP_STATS)

    lines: list[str] = [f"# Agent Digest — {date_str}", ""]

    lines.append("## Identity")
    lines.append(identity if identity else "_No completed tasks yet._")
    lines.append("")

    if trajectory:
        lines.append("## Trajectory")
        lines.append(trajectory)
        lines.append("")

    if beliefs:
        lines.append("## Active Beliefs (top patterns)")
        for p in beliefs:
            lines.append(f"- [{p['confidence']:.2f} · impact {p['impact']:.2f}] {p['text']}")
        lines.append("")

    if fading:
        lines.append("## Fading (review if encountered)")
        for p in fading:
            lines.append(f"- [{p['confidence']:.2f}] {p['text']}")
        lines.append("")

    if breakthroughs:
        lines.append("## Recent Breakthroughs (last 7 days)")
        for b in breakthroughs:
            lines.append(f"- **{b['task_id']}** — {b['insight']}")
        lines.append("")

    if preferences:
        lines.append("## Preferences")
        for p in preferences:
            lines.append(f"- {p['text']}")
        lines.append("")

    # Stats last + lowest priority — honest success rates, NOT learnings. Placed
    # at the end so they are first to drop under the budget cap (bury the noise).
    if stats:
        lines.append("## Project Stats (success rates — not lessons)")
        for s in stats:
            lines.append(f"- {s['text']}")
        lines.append("")

    body = "\n".join(lines).rstrip() + "\n"
    if len(body) > _RENDER_BUDGET_CHARS:
        body = body[:_RENDER_BUDGET_CHARS].rstrip() + "\n\n…[truncated]\n"
    return body


# ---------------------------------------------------------------------------
# Collectors — each returns structured dicts the renderer formats
# ---------------------------------------------------------------------------


def _collect_identity(conn: sqlite3.Connection) -> str:
    """Summarise task_outcomes over the last 30 days into a single line."""
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS n, "
            "SUM(CASE WHEN outcome='success' THEN 1 ELSE 0 END) AS succ "
            "FROM task_outcomes "
            "WHERE created_at >= datetime('now', '-30 days')"
        ).fetchone()
    except sqlite3.OperationalError:
        return ""
    if not row or not row["n"]:
        return ""
    n = row["n"]
    succ = row["succ"] or 0
    rate = succ / n if n else 0.0

    top_domains = _top_domains(conn)
    domains_str = ", ".join(f"{d} ({c})" for d, c in top_domains) or "—"
    return f"{n} tasks completed (last 30d). Success rate: {rate:.0%}. Top domains: {domains_str}."


def _top_domains(conn: sqlite3.Connection, k: int = 3) -> list[tuple[str, int]]:
    try:
        rows = conn.execute(
            "SELECT domain, COUNT(*) AS n FROM task_outcomes "
            "WHERE created_at >= datetime('now', '-30 days') "
            "GROUP BY domain ORDER BY n DESC LIMIT ?",
            (k,),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    return [(r["domain"] or "—", r["n"]) for r in rows]


def _collect_beliefs(conn: sqlite3.Connection, *, limit: int) -> list[dict]:
    """Top belief patterns by (confidence × impact), confidence ≥ _ACTIVE_MIN.

    Excludes memory_type='stat' (success-rate baselines) — a statistic is not
    a learned lesson. See docs/engineering/learning-extraction.md.
    """
    try:
        rows = conn.execute(
            "SELECT pattern, confidence, impact_score "
            "FROM learned_patterns "
            "WHERE confidence >= ? "
            "  AND COALESCE(memory_type, '') != 'stat' "
            "  AND promoted_to IS NULL "
            "ORDER BY (confidence * COALESCE(impact_score, 0.5)) DESC, "
            "         last_validated DESC, confidence DESC "
            "LIMIT ?",
            (_ACTIVE_MIN, limit),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    return [
        {
            "text": (r["pattern"] or "")[:120],
            "confidence": r["confidence"] or 0.0,
            "impact": r["impact_score"] or 0.5,
        }
        for r in rows
        if r["pattern"]
    ]


def _collect_stats(conn: sqlite3.Connection, *, limit: int) -> list[dict]:
    """Success-rate baselines (memory_type='stat') — shown as honest project
    stats, clearly separated from learned lessons (never ranked as beliefs)."""
    try:
        rows = conn.execute(
            "SELECT pattern FROM learned_patterns "
            "WHERE memory_type = 'stat' "
            "ORDER BY confidence DESC LIMIT ?",
            (limit,),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    return [{"text": (r["pattern"] or "")[:120]} for r in rows if r["pattern"]]


def _collect_fading(conn: sqlite3.Connection, *, limit: int) -> list[dict]:
    """Patterns whose confidence sits in the fading window and are established."""
    try:
        rows = conn.execute(
            "SELECT pattern, confidence "
            "FROM learned_patterns "
            "WHERE confidence BETWEEN ? AND ? "
            "  AND times_seen >= 1 "
            "  AND COALESCE(memory_type, '') != 'stat' "
            "  AND promoted_to IS NULL "
            "ORDER BY confidence ASC LIMIT ?",
            (_FADING_MIN, _FADING_MAX, limit),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    return [
        {"text": (r["pattern"] or "")[:120], "confidence": r["confidence"] or 0.0}
        for r in rows
        if r["pattern"]
    ]


def _collect_breakthroughs(conn: sqlite3.Connection, *, limit: int) -> list[dict]:
    try:
        rows = conn.execute(
            "SELECT task_id, narrative_key_insight "
            "FROM outcome_history "
            "WHERE is_breakthrough = 1 "
            "  AND narrative_key_insight IS NOT NULL "
            "  AND created_at >= datetime('now', '-7 days') "
            "ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    return [
        {"task_id": r["task_id"], "insight": (r["narrative_key_insight"] or "")[:160]}
        for r in rows
        if r["narrative_key_insight"]
    ]


def _collect_preferences(conn: sqlite3.Connection, *, limit: int) -> list[dict]:
    """Pull workflow/decision patterns — these encode the agent's preferences."""
    try:
        rows = conn.execute(
            "SELECT pattern "
            "FROM learned_patterns "
            "WHERE memory_type IN ('workflow', 'decision') "
            "  AND confidence >= 0.4 "
            "ORDER BY confidence DESC LIMIT ?",
            (limit,),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    return [{"text": (r["pattern"] or "")[:140]} for r in rows if r["pattern"]]
