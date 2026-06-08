from __future__ import annotations

from pathlib import Path

try:
    from core.thinking_os.database import init_db
    from core.scheduled.error_sweep import (
        SWEEP_SCOPE,
        rollup_fingerprints,
        run_error_sweep,
        select_for_filing,
    )
except ImportError:  # runner path differences
    from thinking_os.database import init_db
    from scheduled.error_sweep import (
        SWEEP_SCOPE,
        rollup_fingerprints,
        run_error_sweep,
        select_for_filing,
    )


def _seed(tmp_path: Path):
    conn = init_db(tmp_path / "coding-os.db")
    rows = [
        ("2026-06-05T01:00:00Z", "ERROR", "cli.x", "boom A", None, "E", None, "s1", None, "fpA"),
        ("2026-06-05T02:00:00Z", "ERROR", "cli.x", "boom A", None, "E", None, "s2", None, "fpA"),
        ("2026-06-05T03:00:00Z", "ERROR", "cli.x", "boom A", None, "E", None, "s2", None, "fpA"),
        ("2026-06-05T04:00:00Z", "FATAL", "cli.y", "boom B", None, None, None, "s1", None, "fpB"),
        ("2026-06-05T05:00:00Z", "WARN", "cli.z", "warn C", None, None, None, "s1", None, "fpC"),
        ("2026-06-05T06:00:00Z", "ERROR", SWEEP_SCOPE, "sweep self", None, None, None, "s1", None, "fpS"),
    ]
    conn.executemany(
        "INSERT INTO log_events "
        "(ts, lvl, scope, msg, kv, exc_type, stack, session_id, trace_id, fingerprint) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    return conn


def test_rollup_excludes_sweep_scope_and_counts(tmp_path: Path) -> None:
    conn = _seed(tmp_path)
    assert rollup_fingerprints(conn) == 3  # fpA, fpB, fpC — fpS (ops.error_sweep) excluded
    a = conn.execute(
        "SELECT count, distinct_sessions, max_lvl FROM log_fingerprints WHERE fingerprint='fpA'"
    ).fetchone()
    assert tuple(a) == (3, 2, "ERROR")
    assert conn.execute(
        "SELECT count(*) FROM log_fingerprints WHERE fingerprint='fpS'"
    ).fetchone()[0] == 0


def test_select_thresholds(tmp_path: Path) -> None:
    conn = _seed(tmp_path)
    rollup_fingerprints(conn)
    sel = {r["fingerprint"]: sev for r, sev in select_for_filing(conn, occ_threshold=3, session_threshold=2)}
    assert sel.get("fpB") == "fatal"  # FATAL always files
    assert sel.get("fpA") == "error"  # 3 occurrences >= 3
    assert "fpC" not in sel  # WARN, 1 occurrence — below threshold


def test_sessionless_error_cluster_is_not_filed(tmp_path: Path) -> None:
    """A recurring ERROR with no real session (session_id NULL) is test/machine
    noise, not an agent-visible bug — it must never be filed (TASK-243/244)."""
    conn = init_db(tmp_path / "coding-os.db")
    rows = [
        # 4 occurrences, ALL session-less — over occ_threshold but distinct_sessions=0
        ("2026-06-05T01:00:00Z", "ERROR", "tools._shared", "boom", None, None, None, None, None, "fpN"),
        ("2026-06-05T02:00:00Z", "ERROR", "tools._shared", "boom", None, None, None, None, None, "fpN"),
        ("2026-06-05T03:00:00Z", "ERROR", "tools._shared", "boom", None, None, None, None, None, "fpN"),
        ("2026-06-05T04:00:00Z", "ERROR", "tools._shared", "boom", None, None, None, None, None, "fpN"),
        # a FATAL with no session still files — safety overrides the session guard
        ("2026-06-05T05:00:00Z", "FATAL", "cli.boot", "dead", None, None, None, None, None, "fpF"),
    ]
    conn.executemany(
        "INSERT INTO log_events "
        "(ts, lvl, scope, msg, kv, exc_type, stack, session_id, trace_id, fingerprint) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    rollup_fingerprints(conn)
    sel = {r["fingerprint"]: sev for r, sev in select_for_filing(conn, occ_threshold=3, session_threshold=2)}
    assert "fpN" not in sel  # session-less ERROR cluster — suppressed
    assert sel.get("fpF") == "fatal"  # FATAL always files regardless of session


def test_run_sweep_files_once_idempotent(tmp_path: Path) -> None:
    conn = _seed(tmp_path)
    created: list = []

    def fake_create(row, severity):
        tid = f"TASK-{900 + len(created)}"
        created.append((row["fingerprint"], severity, tid))
        return tid

    first = run_error_sweep(conn, create_bug_task=fake_create, occ_threshold=3, session_threshold=2)
    assert len(first["filed"]) == 2  # fpA + fpB
    second = run_error_sweep(conn, create_bug_task=fake_create, occ_threshold=3, session_threshold=2)
    assert second["filed"] == []  # already filed → idempotent
    assert len(created) == 2


def test_dry_run_files_nothing(tmp_path: Path) -> None:
    conn = _seed(tmp_path)
    called: list = []
    result = run_error_sweep(
        conn,
        create_bug_task=lambda *a: called.append(a) or "X",
        occ_threshold=3,
        session_threshold=2,
        dry_run=True,
    )
    assert called == []
    assert all(f.get("dry_run") for f in result["filed"])
    assert conn.execute(
        "SELECT count(*) FROM log_fingerprints WHERE status='filed'"
    ).fetchone()[0] == 0
