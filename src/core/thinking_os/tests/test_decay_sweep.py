"""
Tests for confidence decay script (TASK-139).

Covers exponential decay formula, effective_decay_rate anti-forgetting,
archive logic, working memory cleanup, and absent DB handling.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import init_db
from decay import (
    run_decay,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    c = init_db(tmp_path / "test.db")
    yield c
    c.close()


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    p = tmp_path / "decay_test.db"
    c = init_db(p)
    c.close()
    return p


# ---------------------------------------------------------------------------
# Regression — fresh pattern must survive the first decay run (audit N1 / 1a)
# ---------------------------------------------------------------------------


class TestArchivedAtPruneGrace:
    @staticmethod
    def _insert_archived(c: sqlite3.Connection, archived_offset: str) -> int:
        cur = c.execute(
            "INSERT INTO learned_patterns "
            "(pattern, memory_type, domain, source, confidence, times_validated, "
            "promoted_to, created_at, last_validated, last_accessed_at, archived_at) "
            "VALUES (?, 'pattern', 'TEST', 'mined', 0.1, 0, 'archived', "
            "datetime('now','-200 days'), datetime('now','-200 days'), "
            "datetime('now','-200 days'), datetime('now', ?))",
            (f"archived {archived_offset}", archived_offset),
        )
        return int(cur.lastrowid)

    def test_recently_archived_survives_prune(self, db_path: Path) -> None:
        c = init_db(db_path)
        pid = self._insert_archived(c, "-1 days")
        c.commit()
        c.close()
        run_decay(db_path)
        c2 = init_db(db_path)
        row = c2.execute("SELECT id FROM learned_patterns WHERE id = ?", (pid,)).fetchone()
        c2.close()
        assert row is not None, "freshly-archived pattern pruned inside the grace window"

    def test_long_archived_is_pruned(self, db_path: Path) -> None:
        c = init_db(db_path)
        pid = self._insert_archived(c, "-120 days")
        c.commit()
        c.close()
        run_decay(db_path)
        c2 = init_db(db_path)
        row = c2.execute("SELECT id FROM learned_patterns WHERE id = ?", (pid,)).fetchone()
        c2.close()
        assert row is None, "long-dormant archived pattern should be pruned"


class TestRunDecayLocked:
    def test_throttle_skips_second_run(self, db_path: Path) -> None:
        from decay import run_decay_locked

        first = run_decay_locked(db_path, throttle_days=7)
        assert first["status"] == "ok"
        second = run_decay_locked(db_path, throttle_days=7)
        assert second["status"] == "skipped"

    def test_zero_throttle_always_runs(self, db_path: Path) -> None:
        from decay import run_decay_locked

        run_decay_locked(db_path, throttle_days=0)
        again = run_decay_locked(db_path, throttle_days=0)
        assert again["status"] == "ok"


class TestRunDecay:
    def test_absent_db(self, tmp_path: Path) -> None:
        result = run_decay(tmp_path / "nonexistent.db")
        assert result["status"] == "no_db"

    def test_empty_db(self, db_path: Path) -> None:
        result = run_decay(db_path)
        assert result["total_patterns"] == 0
        assert result["decayed"] == 0

    def test_decays_old_pattern(self, db_path: Path) -> None:
        conn = init_db(db_path)
        try:
            conn.execute(
                "INSERT INTO learned_patterns (pattern, confidence, decay_rate, "
                "last_validated, times_validated, impact_score) "
                "VALUES (?, ?, ?, datetime('now', '-90 days'), ?, ?)",
                ("Old pattern", 0.7, 0.1, 1, 0.5),
            )
            conn.commit()
        finally:
            conn.close()

        result = run_decay(db_path)
        assert result["decayed"] >= 1

        # Verify confidence decreased
        conn = init_db(db_path)
        try:
            row = conn.execute(
                "SELECT confidence FROM learned_patterns WHERE pattern = 'Old pattern'"
            ).fetchone()
            assert row[0] < 0.7
        finally:
            conn.close()

    def test_archives_at_floor(self, db_path: Path) -> None:
        conn = init_db(db_path)
        try:
            conn.execute(
                "INSERT INTO learned_patterns (pattern, confidence, decay_rate, "
                "last_validated, times_validated, impact_score) "
                "VALUES (?, ?, ?, datetime('now', '-365 days'), ?, ?)",
                ("Very old pattern", 0.15, 0.1, 0, 0.5),
            )
            conn.commit()
        finally:
            conn.close()

        result = run_decay(db_path)
        assert result["archived"] >= 1

        conn = init_db(db_path)
        try:
            row = conn.execute(
                "SELECT promoted_to FROM learned_patterns WHERE pattern = 'Very old pattern'"
            ).fetchone()
            assert row[0] == "archived"
        finally:
            conn.close()

    def test_skips_already_archived(self, db_path: Path) -> None:
        conn = init_db(db_path)
        try:
            conn.execute(
                "INSERT INTO learned_patterns (pattern, confidence, promoted_to) VALUES (?, ?, ?)",
                ("Archived pattern", 0.1, "archived"),
            )
            conn.commit()
        finally:
            conn.close()

        result = run_decay(db_path)
        assert result["total_patterns"] == 0  # archived excluded

    def test_protected_pattern_unchanged(self, db_path: Path) -> None:
        conn = init_db(db_path)
        try:
            conn.execute(
                "INSERT INTO learned_patterns (pattern, confidence, decay_rate, "
                "last_validated, last_accessed_at, times_validated, impact_score) "
                "VALUES (?, ?, ?, datetime('now', '-90 days'), datetime('now', '-3 days'), ?, ?)",
                ("Protected pattern", 0.7, 0.1, 10, 0.9),
            )
            conn.commit()
        finally:
            conn.close()

        result = run_decay(db_path)
        assert result["unchanged"] >= 1

    def test_dry_run_no_changes(self, db_path: Path) -> None:
        conn = init_db(db_path)
        try:
            conn.execute(
                "INSERT INTO learned_patterns (pattern, confidence, decay_rate, "
                "last_validated, times_validated, impact_score) "
                "VALUES (?, ?, ?, datetime('now', '-90 days'), ?, ?)",
                ("Dry run test", 0.7, 0.1, 1, 0.5),
            )
            conn.commit()
        finally:
            conn.close()

        run_decay(db_path, dry_run=True)

        conn = init_db(db_path)
        try:
            row = conn.execute(
                "SELECT confidence FROM learned_patterns WHERE pattern = 'Dry run test'"
            ).fetchone()
            assert row[0] == 0.7  # unchanged
        finally:
            conn.close()

    def test_working_memory_cleanup(self, db_path: Path) -> None:
        conn = init_db(db_path)
        try:
            conn.execute(
                "INSERT INTO observations (title, memory_type, expires_at) "
                "VALUES (?, ?, datetime('now', '-1 hour'))",
                ("Expired working memory", "working"),
            )
            conn.execute(
                "INSERT INTO observations (title, memory_type, expires_at) "
                "VALUES (?, ?, datetime('now', '+1 hour'))",
                ("Active working memory", "working"),
            )
            conn.execute(
                "INSERT INTO observations (title, memory_type) VALUES (?, ?)",
                ("Permanent observation", "discovery"),
            )
            conn.commit()
        finally:
            conn.close()

        result = run_decay(db_path)
        assert result["working_memory_cleaned"] == 1

        conn = init_db(db_path)
        try:
            count = conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
            assert count == 2  # active + permanent remain
        finally:
            conn.close()


class TestConsolidation:
    """G7 — merge exact duplicates + prune long-dead archived patterns."""

    def _insert(self, conn: sqlite3.Connection, **kw: object) -> None:
        cols = ", ".join(kw.keys())
        ph = ", ".join("?" for _ in kw)
        conn.execute(f"INSERT INTO learned_patterns ({cols}) VALUES ({ph})", tuple(kw.values()))

    def test_merges_exact_duplicates(self, db_path: Path) -> None:
        conn = init_db(db_path)
        try:
            self._insert(
                conn,
                pattern="Dup",
                domain="X",
                confidence=0.8,
                decay_rate=0.1,
                last_validated="now",
                times_validated=1,
                impact_score=0.5,
                access_count=3,
            )
            self._insert(
                conn,
                pattern="Dup",
                domain="X",
                confidence=0.6,
                decay_rate=0.1,
                last_validated="now",
                times_validated=2,
                impact_score=0.5,
                access_count=5,
            )
            conn.execute("UPDATE learned_patterns SET last_validated = datetime('now')")
            conn.commit()
        finally:
            conn.close()

        result = run_decay(db_path)
        assert result["merged"] == 1

        conn = init_db(db_path)
        try:
            rows = conn.execute(
                "SELECT access_count, times_validated FROM learned_patterns WHERE pattern='Dup'"
            ).fetchall()
            assert len(rows) == 1  # one survivor
            assert rows[0][0] == 8  # 3 + 5 access folded in
            assert rows[0][1] == 3  # 1 + 2 validations folded in
        finally:
            conn.close()

    def test_prunes_dead_archived(self, db_path: Path) -> None:
        conn = init_db(db_path)
        try:
            self._insert(
                conn,
                pattern="Dead",
                domain="X",
                confidence=0.10,
                decay_rate=0.1,
                last_validated="now",
                times_seen=0,
                impact_score=0.5,
                promoted_to="archived",
            )
            conn.execute(
                "UPDATE learned_patterns SET last_accessed_at = datetime('now','-120 days')"
            )
            conn.commit()
        finally:
            conn.close()

        result = run_decay(db_path, archive_prune_days=90)
        assert result["pruned"] == 1

        conn = init_db(db_path)
        try:
            assert conn.execute("SELECT COUNT(*) FROM learned_patterns").fetchone()[0] == 0
        finally:
            conn.close()

    def test_keeps_deeply_seen_archived(self, db_path: Path) -> None:
        conn = init_db(db_path)
        try:
            self._insert(
                conn,
                pattern="Important",
                domain="X",
                confidence=0.10,
                decay_rate=0.1,
                last_validated="now",
                times_seen=7,
                impact_score=0.9,
                promoted_to="archived",
            )
            conn.execute(
                "UPDATE learned_patterns SET last_accessed_at = datetime('now','-200 days')"
            )
            conn.commit()
        finally:
            conn.close()

        result = run_decay(db_path, archive_prune_days=90)
        assert result["pruned"] == 0  # times_seen>=5 (established) survives

    def test_keeps_recently_accessed_archived(self, db_path: Path) -> None:
        conn = init_db(db_path)
        try:
            self._insert(
                conn,
                pattern="Recent",
                domain="X",
                confidence=0.10,
                decay_rate=0.1,
                last_validated="now",
                times_seen=0,
                impact_score=0.5,
                promoted_to="archived",
            )
            conn.execute("UPDATE learned_patterns SET last_accessed_at = datetime('now','-2 days')")
            conn.commit()
        finally:
            conn.close()

        result = run_decay(db_path, archive_prune_days=90)
        assert result["pruned"] == 0  # accessed within window survives


class TestExpiredObservationGC:
    def test_decay_gcs_expired_and_spares_null(self, tmp_path: Path) -> None:
        db_path = tmp_path / "gc.db"
        c = init_db(db_path)
        c.execute(
            "INSERT INTO observations (session_id, tool_name, title, memory_type, expires_at) "
            "VALUES ('s', 'Edit', 'expired-row', 'changelog', '2000-01-01 00:00:00')"
        )
        c.execute(
            "INSERT INTO observations (session_id, tool_name, title, memory_type, expires_at) "
            "VALUES ('s', 'Edit', 'permanent-row', 'discovery', NULL)"
        )
        c.commit()
        c.close()
        run_decay(db_path)
        c2 = init_db(db_path)
        titles = [r[0] for r in c2.execute("SELECT title FROM observations").fetchall()]
        c2.close()
        assert "expired-row" not in titles  # past-expiry row GC'd
        assert "permanent-row" in titles  # NULL-expiry legacy row spared
