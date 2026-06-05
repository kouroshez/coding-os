from __future__ import annotations

import sqlite3
from typing import Callable

# Reserved scope for the sweep's own diagnostics — EXCLUDED from its input so a
# sweep error can never file a bug task about itself (anti-recursion invariant).
SWEEP_SCOPE = "ops.error_sweep"

_SEV = {"DEBUG": 10, "INFO": 20, "OK": 21, "WARN": 30, "ERROR": 40, "FATAL": 50}


def rollup_fingerprints(conn: sqlite3.Connection) -> int:
    """Recompute log_fingerprints aggregates from log_events. Idempotent. Returns fingerprint count."""
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT fingerprint, scope, exc_type, msg, lvl, ts, session_id "
        "FROM log_events WHERE scope != ? AND lvl IN ('WARN', 'ERROR', 'FATAL')",
        (SWEEP_SCOPE,),
    ).fetchall()
    agg: dict[str, dict] = {}
    for r in rows:
        a = agg.get(r["fingerprint"])
        if a is None:
            a = agg[r["fingerprint"]] = {
                "scope": r["scope"], "exc_type": r["exc_type"], "sample_msg": r["msg"],
                "max_lvl": r["lvl"], "first_seen": r["ts"], "last_seen": r["ts"],
                "count": 0, "sessions": set(),
            }
        a["count"] += 1
        if r["ts"] < a["first_seen"]:
            a["first_seen"] = r["ts"]
        if r["ts"] > a["last_seen"]:
            a["last_seen"] = r["ts"]
        if _SEV.get(r["lvl"], 0) > _SEV.get(a["max_lvl"], 0):
            a["max_lvl"] = r["lvl"]
            a["sample_msg"] = r["msg"]
        if r["session_id"]:
            a["sessions"].add(r["session_id"])
    for fp, a in agg.items():
        conn.execute(
            "INSERT INTO log_fingerprints "
            "(fingerprint, scope, exc_type, sample_msg, max_lvl, first_seen, last_seen, "
            " count, distinct_sessions) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(fingerprint) DO UPDATE SET "
            "  last_seen = excluded.last_seen, count = excluded.count, "
            "  distinct_sessions = excluded.distinct_sessions, max_lvl = excluded.max_lvl, "
            "  sample_msg = excluded.sample_msg",
            (fp, a["scope"], a["exc_type"], a["sample_msg"], a["max_lvl"],
             a["first_seen"], a["last_seen"], a["count"], len(a["sessions"])),
        )
    conn.commit()
    return len(agg)


def select_for_filing(
    conn: sqlite3.Connection, *, occ_threshold: int, session_threshold: int
) -> list[tuple[sqlite3.Row, str]]:
    """Open fingerprints worth a task: FATAL always, ERROR past occurrence/session threshold."""
    conn.row_factory = sqlite3.Row
    out: list[tuple[sqlite3.Row, str]] = []
    for r in conn.execute("SELECT * FROM log_fingerprints WHERE status = 'open'").fetchall():
        if r["max_lvl"] == "FATAL":
            out.append((r, "fatal"))
        elif r["count"] >= occ_threshold or r["distinct_sessions"] >= session_threshold:
            out.append((r, "error"))
    return out


def run_error_sweep(
    conn: sqlite3.Connection,
    *,
    create_bug_task: Callable[[sqlite3.Row, str], "str | None"],
    occ_threshold: int = 3,
    session_threshold: int = 2,
    dry_run: bool = False,
) -> dict:
    """Roll up, select over-threshold fingerprints, and file one idempotent bug task each.

    create_bug_task(row, severity) -> task_id is injected so the sweep logic stays
    pure + testable. Idempotent: only status='open' fingerprints are filed; once
    filed they flip to 'filed' and are never re-selected.
    """
    rolled = rollup_fingerprints(conn)
    candidates = select_for_filing(
        conn, occ_threshold=occ_threshold, session_threshold=session_threshold
    )
    filed: list[dict] = []
    for row, severity in candidates:
        if dry_run:
            filed.append({"fingerprint": row["fingerprint"], "severity": severity, "dry_run": True})
            continue
        task_id = create_bug_task(row, severity)
        if task_id:
            conn.execute(
                "UPDATE log_fingerprints SET task_id = ?, status = 'filed' WHERE fingerprint = ?",
                (task_id, row["fingerprint"]),
            )
            filed.append(
                {"fingerprint": row["fingerprint"], "task_id": task_id, "severity": severity}
            )
    conn.commit()
    return {"rolled_up": rolled, "candidates": len(candidates), "filed": filed}
