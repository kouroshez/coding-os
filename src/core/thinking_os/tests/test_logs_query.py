from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

try:
    from core.thinking_os.database import init_db
    from core.thinking_os.tools.logs import log_query
except ImportError:  # path layout differs by runner
    from thinking_os.database import init_db
    from thinking_os.tools.logs import log_query


def _db_with_events(tmp_path: Path) -> sqlite3.Connection:
    conn = init_db(tmp_path / "coding-os.db")
    rows = [
        ("2026-06-05T01:00:00Z", "WARN", "cli.doctor", "disk almost full",
         None, None, None, None, None, "fp1"),
        ("2026-06-05T02:00:00Z", "ERROR", "thinking_os.server", "db migration v23 failed",
         None, "RuntimeError", None, "sesA", None, "fp2"),
        ("2026-06-05T03:00:00Z", "FATAL", "cli.main", "uv not on PATH",
         None, None, None, "sesB", None, "fp3"),
    ]
    conn.executemany(
        "INSERT INTO log_events "
        "(ts, lvl, scope, msg, kv, exc_type, stack, session_id, trace_id, fingerprint) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    return conn


def test_level_floor_in_set(tmp_path: Path) -> None:
    result = log_query(_db_with_events(tmp_path), level="error")
    assert result["total"] == 2
    assert {r["lvl"] for r in result["rows"]} == {"ERROR", "FATAL"}  # WARN excluded


def test_scope_glob(tmp_path: Path) -> None:
    result = log_query(_db_with_events(tmp_path), scope="cli.*")
    assert {r["scope"] for r in result["rows"]} == {"cli.doctor", "cli.main"}


def test_msg_search(tmp_path: Path) -> None:
    result = log_query(_db_with_events(tmp_path), search="migration")
    assert result["total"] == 1
    assert result["rows"][0]["scope"] == "thinking_os.server"


def test_most_recent_first(tmp_path: Path) -> None:
    result = log_query(_db_with_events(tmp_path))
    assert result["rows"][0]["ts"] == "2026-06-05T03:00:00Z"


def test_session_filter(tmp_path: Path) -> None:
    result = log_query(_db_with_events(tmp_path), session_id="sesA")
    assert result["total"] == 1
    assert result["rows"][0]["lvl"] == "ERROR"


def test_invalid_level_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        log_query(_db_with_events(tmp_path), level="bogus")
