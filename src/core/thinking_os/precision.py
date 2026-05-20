"""
Coding OS — Retrieval precision tracker + contextual enrichment stub (Phase G.11).

Purpose
-------
Decide whether we need the expensive Anthropic "Contextual Retrieval" pre-step
(add an LLM-generated one-sentence context to each chunk before embedding).
The published benchmark claims ~49% retrieval-failure reduction, but the token
cost scales with the corpus size. Per the plan doc we ONLY activate this when
real-world precision drops below a threshold.

This module ships:

  1. `precision_snapshot(conn, *, lookback_days=30)` — computes a single scalar
     in [0.0, 1.0] that approximates retrieval precision, using existing
     retrievals/outcome data. No new schema.

     Signal:
         precision = ( cited-success + passive-success ) / total-resolved
     where "resolved" means the retrieval row has a non-null outcome mapped
     to either the success set or the fail set. Priorities aren't used —
     precision is upstream of priority learning (G.8).

  2. `should_enable_contextual_enrichment(conn)` — the trigger gate. Returns
     (decision_bool, reason_str, snapshot_dict). False if precision is OK
     or if the sample is too small to matter (default min_sample=30). Never
     recommends enabling on empty data.

  3. `contextual_enrichment_stub(heading_path, content, doc_title="")` —
     a PURE placeholder that returns the chunk untouched plus a status dict
     reporting "would_enrich=True" when called. NO LLM is invoked. This is
     the chokepoint where a future Anthropic Haiku call wires in; callers
     use the same interface today so activating enrichment later is a 1-line
     swap, not a refactor.

Design guardrail: we are NOT generating AI context in this phase. The cost
+ dependency implications need explicit user opt-in (separate Phase G.12).
This module only measures and advertises the gate.

Public API
----------
PRECISION_TARGET             — float (0.7 per plan doc)
MIN_SAMPLE_FOR_DECISION      — int (30 retrievals)
precision_snapshot(conn, *, lookback_days=30) -> PrecisionSnapshot
should_enable_contextual_enrichment(conn, ...) -> (bool, str, dict)
contextual_enrichment_stub(heading_path, content, doc_title="") -> dict
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import asdict, dataclass
from typing import Optional

logger = logging.getLogger("coding_os.precision")

# Per the brain-hardening plan: trigger enrichment only below 0.70 precision.
# Source: docs/phase-g-brain-hardening-plan.md §G.11.
PRECISION_TARGET: float = 0.70

# Below this sample size the precision estimate is too noisy to act on.
MIN_SAMPLE_FOR_DECISION: int = 30

# Outcome mappings — mirrors tools/retrieve.py so the two modules agree on
# what "success" and "fail" mean.
_SUCCESS_OUTCOMES = frozenset({"success", "done"})
_FAIL_OUTCOMES = frozenset({"rework", "blocked", "failed"})


@dataclass(frozen=True)
class PrecisionSnapshot:
    """Immutable summary of retrieval precision over a lookback window.

    Attributes:
        lookback_days: window the snapshot covers.
        total_retrievals: rows in retrievals table with non-null outcome.
        successes: count where outcome ∈ _SUCCESS_OUTCOMES.
        failures: count where outcome ∈ _FAIL_OUTCOMES.
        unresolved: count of rows with outcome NULL/wip/other.
        precision: successes / (successes + failures), 0.0 when denom is 0.
        sufficient_sample: True when successes+failures ≥ MIN_SAMPLE_FOR_DECISION.
    """

    lookback_days: int
    total_retrievals: int
    successes: int
    failures: int
    unresolved: int
    precision: float
    sufficient_sample: bool


def _has_retrievals(conn: sqlite3.Connection) -> bool:
    try:
        conn.execute("SELECT 1 FROM retrievals LIMIT 1")
        return True
    except sqlite3.OperationalError:
        return False


def precision_snapshot(
    conn: sqlite3.Connection,
    *,
    lookback_days: int = 30,
) -> PrecisionSnapshot:
    """Compute a retrieval-precision snapshot from recent retrievals."""
    lookback_days = max(1, int(lookback_days))
    if not _has_retrievals(conn):
        return PrecisionSnapshot(lookback_days, 0, 0, 0, 0, 0.0, False)

    rows = conn.execute(
        "SELECT outcome FROM retrievals WHERE created_at >= datetime('now', '-' || ? || ' days')",
        (lookback_days,),
    ).fetchall()

    successes = 0
    failures = 0
    unresolved = 0
    for r in rows:
        oc = (r["outcome"] or "").lower()
        if not oc:
            unresolved += 1
        elif oc in _SUCCESS_OUTCOMES:
            successes += 1
        elif oc in _FAIL_OUTCOMES:
            failures += 1
        else:
            unresolved += 1

    total = len(rows)
    resolved = successes + failures
    precision = (successes / resolved) if resolved else 0.0
    return PrecisionSnapshot(
        lookback_days=lookback_days,
        total_retrievals=total,
        successes=successes,
        failures=failures,
        unresolved=unresolved,
        precision=precision,
        sufficient_sample=resolved >= MIN_SAMPLE_FOR_DECISION,
    )


def should_enable_contextual_enrichment(
    conn: sqlite3.Connection,
    *,
    lookback_days: int = 30,
    target: float = PRECISION_TARGET,
    min_sample: int = MIN_SAMPLE_FOR_DECISION,
) -> tuple[bool, str, dict]:
    """Return (enable?, reason, snapshot_dict)."""
    snap = precision_snapshot(conn, lookback_days=lookback_days)
    snap_d = asdict(snap)

    if not _has_retrievals(conn):
        return (False, "pre_v10_no_signal", snap_d)

    resolved = snap.successes + snap.failures
    if resolved == 0:
        return (False, "no_resolved_retrievals_yet", snap_d)
    if resolved < int(min_sample):
        return (
            False,
            f"insufficient_sample: {resolved} resolved < {min_sample}",
            snap_d,
        )
    if snap.precision >= target:
        return (
            False,
            f"precision {snap.precision:.2f} >= target {target:.2f}",
            snap_d,
        )
    return (
        True,
        f"precision {snap.precision:.2f} < target {target:.2f} over {resolved} retrievals",
        snap_d,
    )


def contextual_enrichment_stub(
    heading_path: str,
    content: str,
    doc_title: str = "",
) -> dict:
    """Placeholder for Anthropic-style Contextual Retrieval enrichment."""
    return {
        "enriched_content": content,
        "would_enrich": True,
        "model": None,
        "reason": "stub_only_no_llm_call",
        "heading_path": heading_path,
        "doc_title": doc_title,
    }
