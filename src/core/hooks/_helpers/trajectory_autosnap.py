"""Session-end helper — auto-generate project trajectory snapshot."""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timezone

# Map formula_id prefixes to domain labels shown in trajectory focus line
_FORMULA_DOMAIN: dict[str, str] = {
    "researcher": "research",
    "analyst": "analysis",
    "architect": "architecture",
    "implementer": "implementation",
    "reviewer": "review",
    "debugger": "debugging",
    "refactorer": "refactoring",
    "security_auditor": "security",
    "documenter": "documentation",
    "deployer": "deployment",
    "observer": "observability",
}

# Suggested next steps per root_cause — heuristic, data-driven
_NEXT_STEP_HINTS: dict[str, str] = {
    "scope_too_large": "decompose remaining tasks before next session",
    "missing_context": "load relevant docs via cos_doc_search at session start",
    "wrong_model": "use cos_route_model before dispatching formulas",
    "tool_failure": "verify permissions and env vars before next session",
    "spec_ambiguity": "resolve open questions before implementing",
    "env_mismatch": "validate environment configuration at session start",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return (
        conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
        ).fetchone()
        is not None
    )


def _already_snapped(conn: sqlite3.Connection, session_id: str) -> bool:
    """Skip if we already wrote a snapshot for this session (idempotent)."""
    return (
        conn.execute(
            "SELECT 1 FROM project_trajectory WHERE session_id=? LIMIT 1",
            (session_id,),
        ).fetchone()
        is not None
    )


def _dominant_formula(conn: sqlite3.Connection, session_id: str) -> str:
    """Most frequently dispatched formula this session."""
    if not _table_exists(conn, "formula_dispatches"):
        return ""
    row = conn.execute(
        "SELECT formula_id, COUNT(*) AS cnt "
        "FROM formula_dispatches "
        "WHERE session_id=? AND formula_id IS NOT NULL "
        "GROUP BY formula_id ORDER BY cnt DESC LIMIT 1",
        (session_id,),
    ).fetchone()
    return row["formula_id"] if row else ""


def _session_root_causes(conn: sqlite3.Connection, session_id: str) -> list[str]:
    """Unique non-null root_causes from this session's backtrack events."""
    if not _table_exists(conn, "backtrack_events"):
        return []
    try:
        rows = conn.execute(
            "SELECT DISTINCT root_cause FROM backtrack_events "
            "WHERE session_id=? AND root_cause IS NOT NULL",
            (session_id,),
        ).fetchall()
        return [r["root_cause"] for r in rows]
    except sqlite3.OperationalError:
        return []  # anatomy columns (v25) not yet applied


def _backtrack_count(conn: sqlite3.Connection, session_id: str) -> int:
    if not _table_exists(conn, "backtrack_events"):
        return 0
    return conn.execute(
        "SELECT COUNT(*) FROM backtrack_events WHERE session_id=?",
        (session_id,),
    ).fetchone()[0]


_TOOL_FAILURE_THRESHOLD = 2  # observations → auto backtrack_event


def _aggregate_tool_failures(conn: sqlite3.Connection, session_id: str) -> None:
    """If ≥_TOOL_FAILURE_THRESHOLD tool_failure observations this session, ensure
    a backtrack_event(root_cause='tool_failure') exists so trajectory picks it up."""
    if not _table_exists(conn, "observations") or not _table_exists(conn, "backtrack_events"):
        return

    count = conn.execute(
        "SELECT COUNT(*) FROM observations WHERE session_id=? AND observation_type='tool_failure'",
        (session_id,),
    ).fetchone()[0]

    if count < _TOOL_FAILURE_THRESHOLD:
        return

    existing = conn.execute(
        "SELECT 1 FROM backtrack_events WHERE session_id=? AND root_cause='tool_failure' LIMIT 1",
        (session_id,),
    ).fetchone()
    if existing:
        return

    ts = _now_iso()
    try:
        conn.execute(
            "INSERT INTO backtrack_events "
            "(session_id, from_formula, to_formula, reason, ts, root_cause) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                session_id,
                "",
                "",
                f"Auto-aggregated: {count} tool failures captured this session",
                ts,
                "tool_failure",
            ),
        )
        conn.commit()
    except sqlite3.OperationalError:
        return  # root_cause column not yet applied (pre-v25) — skip silently


def _carry_forward(conn: sqlite3.Connection) -> dict:
    """Read latest trajectory for fields to carry forward."""
    if not _table_exists(conn, "project_trajectory"):
        return {}
    row = conn.execute(
        "SELECT phase, open_questions, architectural_decisions "
        "FROM project_trajectory ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if not row:
        return {}
    result: dict = {"phase": row["phase"] or ""}
    try:
        result["open_questions"] = json.loads(row["open_questions"] or "[]")
    except (json.JSONDecodeError, TypeError):
        result["open_questions"] = []
    try:
        result["architectural_decisions"] = json.loads(row["architectural_decisions"] or "[]")
    except (json.JSONDecodeError, TypeError):
        result["architectural_decisions"] = []
    return result


def _recent_domains(conn: sqlite3.Connection) -> list[str]:
    """Domains from last 5 task_outcomes (best proxy for 'this session's work')."""
    if not _table_exists(conn, "task_outcomes"):
        return []
    rows = conn.execute(
        "SELECT DISTINCT domain FROM task_outcomes ORDER BY rowid DESC LIMIT 5"
    ).fetchall()
    return [r["domain"] for r in rows if r["domain"]]


def derive_snapshot(conn: sqlite3.Connection, session_id: str) -> dict | None:
    """Build trajectory snapshot fields from session DB signals."""
    if not _table_exists(conn, "project_trajectory"):
        return None
    if _already_snapped(conn, session_id):
        return None  # idempotent

    carry = _carry_forward(conn)
    dominant = _dominant_formula(conn, session_id)
    root_causes = _session_root_causes(conn, session_id)
    bt_count = _backtrack_count(conn, session_id)
    domains = _recent_domains(conn)

    # current_focus: dominant formula + recent domains
    focus_parts = []
    if dominant:
        label = _FORMULA_DOMAIN.get(dominant.split(".")[0], dominant)
        focus_parts.append(label)
    if domains:
        focus_parts.append(f"domains: {', '.join(domains[:3])}")
    current_focus = "; ".join(focus_parts) if focus_parts else "general development"

    # anti_patterns: from root_causes this session
    anti_patterns: list = []
    if root_causes:
        anti_patterns = [
            {"pattern": rc, "context": f"observed {bt_count} backtracks this session"}
            for rc in root_causes
        ]

    # next_logical_step: hint from most impactful root_cause
    next_step = ""
    for rc in root_causes:
        if rc in _NEXT_STEP_HINTS:
            next_step = _NEXT_STEP_HINTS[rc]
            break

    # confidence: lower when many backtracks, higher when clean session
    confidence = max(0.4, 0.9 - (bt_count * 0.05))

    return {
        "session_id": session_id,
        "phase": carry.get("phase", ""),
        "current_focus": current_focus,
        "architectural_decisions": carry.get("architectural_decisions", []),
        "anti_patterns_discovered": anti_patterns,
        "open_questions": carry.get("open_questions", []),
        "next_logical_step": next_step,
        "confidence": round(confidence, 2),
    }


def write_snapshot(conn: sqlite3.Connection, snap: dict) -> int:
    """Write trajectory snapshot; return new row id."""
    prev = conn.execute("SELECT id FROM project_trajectory ORDER BY id DESC LIMIT 1").fetchone()
    supersedes_id = prev[0] if prev else None

    cur = conn.execute(
        "INSERT INTO project_trajectory "
        "(session_id, phase, current_focus, architectural_decisions, "
        " anti_patterns_discovered, open_questions, next_logical_step, "
        " confidence, created_at, supersedes_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            snap["session_id"],
            snap["phase"] or None,
            snap["current_focus"] or None,
            json.dumps(snap["architectural_decisions"]),
            json.dumps(snap["anti_patterns_discovered"]),
            json.dumps(snap["open_questions"]),
            snap["next_logical_step"] or None,
            snap["confidence"],
            _now_iso(),
            supersedes_id,
        ),
    )
    conn.commit()
    return cur.lastrowid


def main(argv: list[str]) -> int:
    if len(argv) < 4:
        return 0
    session_id, _active_task, db_path = argv[1], argv[2], argv[3]
    if not session_id or not db_path:
        return 0

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row

        _aggregate_tool_failures(conn, session_id)  # B4: tool failures → backtrack
        snap = derive_snapshot(conn, session_id)
        if snap:
            write_snapshot(conn, snap)

        conn.close()
    except Exception:
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
