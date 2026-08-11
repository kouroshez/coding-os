"""cos_learn_validate — confidence movement (LTP/LTD) and the close-the-loop pass.

Confidence is never hand-set: it moves only through the two formulas here, and
every attempt is logged to `pattern_validations` so self-validation can be
throttled and audited.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("thinking_os.learning")

try:  # package import
    from ._learning_mining import (
        _clean_failure_text,
        _failure_cluster_key,
        _friction_kind,
        _normalize_full,
    )
    from ._learning_store import _distill_fingerprint_safe
except ImportError:  # flat import
    from _learning_mining import (  # type: ignore[no-redef,import-not-found]
        _clean_failure_text,
        _failure_cluster_key,
        _friction_kind,
        _normalize_full,
    )
    from _learning_store import _distill_fingerprint_safe  # type: ignore[no-redef,import-not-found]


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
