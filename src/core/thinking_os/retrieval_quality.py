"""
Coding OS — Retrieval quality tracker + contextual-chunk enrichment stub.

Two-part pipeline:
  1. QUALITY TRACKING — every retrieval can be scored (1.0 if cited and the
     task succeeded, 0.0 if retrieved but never cited AND the task reworked,
     nullable otherwise). Mean precision over a rolling window determines
     whether we should run the expensive LLM enrichment path.

  2. CONTEXTUAL ENRICHMENT (GATED STUB) — Anthropic's "Contextual Retrieval"
     technique prepends a 1-sentence situating context to each chunk before
     embedding, lifting recall by ~49% on synonym-heavy queries. The LLM
     call is NOT implemented yet; we ship the scaffolding so the decision
     is metric-driven:

        if mean_precision(last N) < PRECISION_GATE:
            → recommend running enrichment (cost warning included)
        else:
            → stay on cheap heading-path prefix

Public API:
    record_quality_signal(conn, *, retrieval_id, task_id, layer, query,
                          precision, signal_source)
    backfill_quality_from_outcomes(conn, *, lookback_days=7)
    precision_summary(conn, *, lookback_days=14, layer=None)
    enrich_chunk_context_stub(chunk)
    should_enable_enrichment(conn, *, lookback_days=14)
"""

from __future__ import annotations

import logging
import sqlite3

logger = logging.getLogger("coding_os.retrieval_quality")

# Precision threshold below which we recommend contextual enrichment.
# Tuned from Anthropic's Contextual Retrieval benchmark (49% failure reduction):
# at mean precision ~0.7 the LLM pass has enough headroom to justify cost.
PRECISION_GATE = 0.70

# Minimum sample size before recommendation fires — avoids firing on two
# unlucky retrievals on day one.
_MIN_SAMPLE = 30


def _has_quality(conn: sqlite3.Connection) -> bool:
    try:
        conn.execute("SELECT 1 FROM retrieval_quality LIMIT 1")
        return True
    except sqlite3.OperationalError:
        return False


def record_quality_signal(
    conn: sqlite3.Connection,
    *,
    retrieval_id: int,
    task_id: str | None,
    layer: str,
    query: str | None,
    precision: float,
    signal_source: str,
) -> int | None:
    """Insert a precision observation. Fire-and-forget — never raises."""
    if not _has_quality(conn):
        return None

    p = max(0.0, min(1.0, float(precision)))
    try:
        cur = conn.execute(
            "INSERT INTO retrieval_quality "
            "(retrieval_id, task_id, layer, query, precision, signal_source) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (int(retrieval_id), task_id, layer, query, p, signal_source),
        )
        conn.commit()
        return cur.lastrowid
    except sqlite3.OperationalError as exc:
        logger.debug("record_quality_signal skipped: %s", exc)
        return None


def backfill_quality_from_outcomes(
    conn: sqlite3.Connection,
    *,
    lookback_days: int = 7,
) -> dict:
    """Derive a precision signal for each retrievals row with known outcome.

    Rule:
      - was_cited=1 AND outcome in success   → precision = 1.0
      - was_cited=1 AND outcome in fail      → precision = 0.0
      - was_cited=0 AND outcome in success   → precision = 0.5 (neutral)
      - was_cited=0 AND outcome in fail      → precision = 0.0

    Rows already mirrored into retrieval_quality (same retrieval_id) are
    skipped — this function is idempotent.
    """
    if not _has_quality(conn):
        return {"added": 0, "skipped": 0, "status": "pre_v11_no_op"}

    _SUCCESS = ("success", "done")
    _FAIL = ("rework", "blocked", "failed")

    rows = conn.execute(
        "SELECT r.id, r.task_id, r.layer, r.query, r.was_cited, r.outcome "
        "FROM retrievals r "
        "LEFT JOIN retrieval_quality q ON q.retrieval_id = r.id "
        "WHERE r.outcome IS NOT NULL "
        "  AND r.created_at >= datetime('now', '-' || ? || ' days') "
        "  AND q.id IS NULL",
        (int(lookback_days),),
    ).fetchall()

    added = 0
    skipped = 0
    for r in rows:
        outcome_l = (r["outcome"] or "").lower()
        if outcome_l in _SUCCESS and r["was_cited"]:
            p = 1.0
        elif outcome_l in _FAIL and r["was_cited"]:
            p = 0.0
        elif outcome_l in _SUCCESS:
            p = 0.5
        elif outcome_l in _FAIL:
            p = 0.0
        else:
            skipped += 1
            continue
        record_quality_signal(
            conn,
            retrieval_id=r["id"],
            task_id=r["task_id"],
            layer=r["layer"],
            query=r["query"],
            precision=p,
            signal_source="backfill",
        )
        added += 1

    return {"added": added, "skipped": skipped, "status": "ok"}


def precision_summary(
    conn: sqlite3.Connection,
    *,
    lookback_days: int = 14,
    layer: str | None = None,
) -> dict:
    """Return mean precision + sample size for the lookback window."""
    if not _has_quality(conn):
        return {
            "mean_precision": None,
            "samples": 0,
            "below_gate": False,
            "layer": layer,
            "gate": PRECISION_GATE,
            "status": "pre_v11_no_op",
        }

    sql = (
        "SELECT AVG(precision) AS mean, COUNT(*) AS n "
        "FROM retrieval_quality "
        "WHERE created_at >= datetime('now', '-' || ? || ' days')"
    )
    params: list = [int(lookback_days)]
    if layer:
        sql += " AND layer = ?"
        params.append(layer)

    row = conn.execute(sql, params).fetchone()
    n = row["n"] or 0
    mean = float(row["mean"]) if row["mean"] is not None else None

    actionable = n >= _MIN_SAMPLE and mean is not None
    below_gate = actionable and mean < PRECISION_GATE

    return {
        "mean_precision": round(mean, 4) if mean is not None else None,
        "samples": n,
        "below_gate": bool(below_gate),
        "layer": layer,
        "gate": PRECISION_GATE,
        "min_sample": _MIN_SAMPLE,
        "status": "ok" if actionable else "insufficient_data",
    }


def should_enable_enrichment(
    conn: sqlite3.Connection,
    *,
    lookback_days: int = 14,
) -> dict:
    """Decide whether contextual-chunk enrichment should be turned on.

    Combines the precision summary with an explicit cost warning so the
    caller never enables enrichment blindly.
    """
    summary = precision_summary(conn, lookback_days=lookback_days)
    if summary["status"] != "ok":
        return {
            "recommend": False,
            "reason": f"insufficient_data ({summary['samples']} < {_MIN_SAMPLE})",
            "summary": summary,
        }
    if not summary["below_gate"]:
        return {
            "recommend": False,
            "reason": (
                f"precision {summary['mean_precision']:.2f} ≥ gate "
                f"{PRECISION_GATE} — no enrichment needed"
            ),
            "summary": summary,
        }
    return {
        "recommend": True,
        "reason": (
            f"precision {summary['mean_precision']:.2f} below gate "
            f"{PRECISION_GATE} over {summary['samples']} samples — enrichment "
            "may help (Anthropic Contextual Retrieval, ~49% failure reduction)"
        ),
        "cost_warning": (
            "enrichment triggers one Haiku call per chunk at index time; "
            "~$1 per 400K tokens of doc corpus. Run `make docs-enrich` "
            "when ready (NOT YET IMPLEMENTED)."
        ),
        "summary": summary,
    }


def enrich_chunk_context_stub(chunk: dict) -> dict:
    """Stub for the LLM-generated contextual prefix."""
    return {
        "contextual_prefix": None,
        "context_model": None,
        "status": "stub",
    }
