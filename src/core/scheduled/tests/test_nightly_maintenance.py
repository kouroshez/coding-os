"""Tests for the nightly maintenance legs — graph reindex and VACUUM.

Split from test_nightly.py when it crossed the 500-line gate. These two legs
reclaim or rebuild storage and change for their own reasons; the rest of that
file is state, activity and run orchestration.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

# Make scheduled package importable
_SCHED = Path(__file__).resolve().parents[1]
_THINKING_OS = _SCHED.parent / "thinking_os"
for _p in (_SCHED, _THINKING_OS):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


@pytest.fixture()
def db(tmp_path: Path) -> sqlite3.Connection:
    """Minimal DB with required tables for nightly tasks."""
    db_path = tmp_path / ".coding-os" / "coding-os.db"
    db_path.parent.mkdir(parents=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY, description TEXT);
        INSERT OR IGNORE INTO schema_version VALUES (26, 'test');

        CREATE TABLE IF NOT EXISTS observations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            title TEXT,
            narrative TEXT,
            concepts TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS task_outcomes (
            task_id TEXT PRIMARY KEY,
            type TEXT,
            domain TEXT,
            complexity TEXT,
            outcome TEXT,
            skills_used TEXT,
            model TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS learned_patterns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pattern TEXT,
            memory_type TEXT,
            domain TEXT,
            source TEXT,
            confidence REAL DEFAULT 0.5,
            decay_rate REAL DEFAULT 0.1,
            impact_score REAL DEFAULT 0.5,
            concepts TEXT,
            times_validated INTEGER DEFAULT 0,
            times_violated INTEGER DEFAULT 0,
            access_count INTEGER DEFAULT 0,
            last_accessed_at TEXT,
            promoted_to TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            last_validated TEXT,
            trust_tier TEXT DEFAULT 'volatile',
            provenance TEXT DEFAULT 'agent_learned'
        );

        CREATE TABLE IF NOT EXISTS routing_weights (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            domain TEXT,
            complexity TEXT,
            model TEXT,
            skill TEXT,
            success_rate REAL,
            sample_count INTEGER,
            last_updated TEXT DEFAULT (datetime('now')),
            last_recalc_at TEXT,
            outcomes_at_recalc INTEGER,
            UNIQUE(domain, complexity, model, skill)
        );
    """)
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture()
def project_root(tmp_path: Path, db: Path) -> Path:
    return tmp_path


# ---------------------------------------------------------------------------
# graph_reindex_if_stale (Task 4 — added 2026-05-18)
# ---------------------------------------------------------------------------


class TestGraphReindexIfStale:
    """Nightly reindex covers the gap when no edit fired the PostToolUse hook.

    Staleness is the age of the newest indexed NODE — the same number
    `cos doctor` grades `graph.freshness` on. It used to read
    `.graph-backend.json::last_ok_at`, a backend liveness probe refreshed on
    every query, so on any project in use this leg never fired. Observed
    2026-09-15: nightly logged `skipped, fresh (38050s)` while doctor called
    the index stale at 121176s six hours later.
    """

    def _write_index(self, project_root: Path, updated_at: int) -> Path:
        """Seed one graph node so the leg has an index age to read."""
        import sqlite3

        state = project_root / ".coding-os"
        state.mkdir(parents=True, exist_ok=True)
        db = state / "coding-os.db"
        with sqlite3.connect(db) as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS graph_nodes (uid TEXT PRIMARY KEY, updated_at INTEGER)"
            )
            conn.execute(
                "INSERT OR REPLACE INTO graph_nodes (uid, updated_at) VALUES (?, ?)",
                ("code:file:sample.py", updated_at),
            )
        return db

    def test_skips_when_no_index_yet(self, tmp_path: Path) -> None:
        import nightly

        result = nightly._run_graph_reindex_if_stale(tmp_path, dry_run=False)
        assert result == {"status": "skipped", "reason": "no_graph_index_yet"}

    def test_skips_when_index_is_fresh(self, tmp_path: Path) -> None:
        import time as _t

        import nightly

        self._write_index(tmp_path, int(_t.time()) - 60)  # 60s old
        result = nightly._run_graph_reindex_if_stale(tmp_path, dry_run=False)
        assert result["status"] == "skipped"
        assert "fresh" in result["reason"]

    def test_a_live_backend_does_not_mask_a_stale_index(self, tmp_path: Path) -> None:
        """The regression itself: a fresh liveness probe beside an old index.

        Under the old reading this returned `skipped, fresh` — the exact case
        the leg exists to repair.
        """
        import time as _t

        import nightly

        now = int(_t.time())
        self._write_index(tmp_path, now - 200_000)  # index >24h old
        probe = tmp_path / ".coding-os" / ".graph-backend.json"
        probe.write_text(json.dumps({"backend": "sqlite", "last_ok_at": now}))

        result = nightly._run_graph_reindex_if_stale(tmp_path, dry_run=True)
        assert result["status"] == "dry_run", "a live backend masked a stale index"
        assert result["would_reindex"] is True

    def test_dry_run_when_index_is_stale(self, tmp_path: Path) -> None:
        import time as _t

        import nightly

        self._write_index(tmp_path, int(_t.time()) - 200_000)  # >24h
        result = nightly._run_graph_reindex_if_stale(tmp_path, dry_run=True)
        assert result["status"] == "dry_run"
        assert result["would_reindex"] is True
        assert result["age_seconds"] >= 200_000

    def test_invokes_subprocess_when_stale(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import time as _t

        import nightly

        self._write_index(tmp_path, int(_t.time()) - 200_000)

        captured: dict = {}

        class _FakeCompleted:
            returncode = 0
            stdout = "[graph-reindex] processed=42 skipped=0 errors=0 duration=1.5s\n"
            stderr = ""

        def _fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            captured["cwd"] = kwargs.get("cwd")
            return _FakeCompleted()

        # Patch subprocess inside the function's local import scope by
        # replacing it on the imported subprocess module reference.
        import subprocess

        monkeypatch.setattr(subprocess, "run", _fake_run)

        result = nightly._run_graph_reindex_if_stale(tmp_path, dry_run=False)
        assert result["status"] == "ok"
        assert "processed=42" in result["summary"]
        assert captured["cmd"][0] == sys.executable
        assert captured["cmd"][1:4] == ["-m", "cli.main", "graph-reindex"]
        assert captured["cwd"] == str(tmp_path)


class TestVacuumIfBloated:
    """SQLite reuses free pages but never hands them back, and nothing called
    VACUUM: it existed as `cos brain-gc --vacuum` and no scheduled leg invoked
    it, so the file only ever grew — and every consumer inherits that.
    """

    @staticmethod
    def _bloated(tmp_path, rows=3000):
        import os
        import sqlite3

        db = tmp_path / "bloat.db"
        conn = sqlite3.connect(db)
        conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, blob BLOB)")
        conn.executemany(
            "INSERT INTO t (blob) VALUES (?)", [(os.urandom(4096),) for _ in range(rows)]
        )
        conn.commit()
        conn.execute("DELETE FROM t")
        conn.commit()
        conn.close()
        return db

    def test_reclaims_bytes_from_a_bloated_database(self, tmp_path: Path) -> None:
        import nightly

        db = self._bloated(tmp_path)
        before = db.stat().st_size
        result = nightly._run_vacuum_if_bloated(db, dry_run=False)
        assert result["status"] == "ok"
        assert result["reclaimed_bytes"] > 0
        assert db.stat().st_size < before

    def test_dry_run_reports_without_touching_the_file(self, tmp_path: Path) -> None:
        import nightly

        db = self._bloated(tmp_path)
        before = db.stat().st_size
        result = nightly._run_vacuum_if_bloated(db, dry_run=True)
        assert result["status"] == "dry_run"
        assert result["would_reclaim_bytes"] > 0
        assert db.stat().st_size == before

    def test_a_tidy_database_is_left_alone(self, tmp_path: Path) -> None:
        """VACUUM takes an exclusive lock; below the floor it costs more than
        the bytes are worth."""
        import sqlite3

        import nightly

        db = tmp_path / "tidy.db"
        sqlite3.connect(db).close()
        result = nightly._run_vacuum_if_bloated(db, dry_run=False)
        assert result["status"] == "skipped"
        assert "free page" in result["reason"]

    def test_a_missing_database_is_skipped_not_an_error(self, tmp_path: Path) -> None:
        import nightly

        assert nightly._run_vacuum_if_bloated(tmp_path / "absent.db", dry_run=False) == {
            "status": "skipped",
            "reason": "no_db",
        }
