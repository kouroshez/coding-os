"""
Tests for precision.py — retrieval precision tracker + enrichment stub (G.11).

Contract:
  - precision_snapshot: counts success/fail/unresolved correctly, precision
    = successes / resolved, tolerates pre-v10 DBs.
  - should_enable_contextual_enrichment: recommends True only when
    (precision < target) AND (sample ≥ min_sample). Never auto-enables on
    empty data.
  - contextual_enrichment_stub: is a pure no-op returning the same content
    with `would_enrich=True, model=None`.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import init_db  # noqa: E402
from precision import (  # noqa: E402
    MIN_SAMPLE_FOR_DECISION,
    PRECISION_TARGET,
    PrecisionSnapshot,
    contextual_enrichment_stub,
    precision_snapshot,
    should_enable_contextual_enrichment,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    c = init_db(tmp_path / "precision.db")
    yield c
    c.close()


def _seed_retrieval(
    conn: sqlite3.Connection,
    outcome: str | None,
    *,
    days_ago: int = 0,
) -> None:
    """Insert one retrievals row with the given outcome and created_at offset."""
    if days_ago > 0:
        created_at = f"datetime('now', '-{days_ago} days')"
        conn.execute(
            "INSERT INTO retrievals "
            "(session_id, task_id, layer, query, source_table, source_id, "
            " score, outcome, created_at) "
            f"VALUES (?, ?, ?, ?, ?, ?, ?, ?, {created_at})",
            ("ses", "TASK-P", "docs", "q", "document_chunks", 1, 0.5, outcome),
        )
    else:
        conn.execute(
            "INSERT INTO retrievals "
            "(session_id, task_id, layer, query, source_table, source_id, score, outcome) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("ses", "TASK-P", "docs", "q", "document_chunks", 1, 0.5, outcome),
        )
    conn.commit()


# ---------------------------------------------------------------------------
# precision_snapshot
# ---------------------------------------------------------------------------

class TestPrecisionSnapshot:
    def test_empty_db(self, conn: sqlite3.Connection) -> None:
        snap = precision_snapshot(conn)
        assert snap.total_retrievals == 0
        assert snap.successes == 0
        assert snap.failures == 0
        assert snap.precision == 0.0
        assert snap.sufficient_sample is False

    def test_pre_v10_returns_zero(self, tmp_path: Path) -> None:
        raw = sqlite3.connect(str(tmp_path / "raw.db"))
        try:
            snap = precision_snapshot(raw)
            assert isinstance(snap, PrecisionSnapshot)
            assert snap.total_retrievals == 0
            assert snap.precision == 0.0
        finally:
            raw.close()

    def test_counts_resolved_only(self, conn: sqlite3.Connection) -> None:
        for _ in range(4):
            _seed_retrieval(conn, "success")
        for _ in range(1):
            _seed_retrieval(conn, "rework")
        _seed_retrieval(conn, None)   # unresolved
        _seed_retrieval(conn, "wip")  # unresolved
        snap = precision_snapshot(conn)
        assert snap.successes == 4
        assert snap.failures == 1
        assert snap.unresolved == 2
        assert snap.precision == pytest.approx(4 / 5)
        assert snap.total_retrievals == 7

    def test_sufficient_sample_threshold(self, conn: sqlite3.Connection) -> None:
        # 29 successes + 0 fails → resolved = 29 < MIN_SAMPLE_FOR_DECISION (30)
        for _ in range(MIN_SAMPLE_FOR_DECISION - 1):
            _seed_retrieval(conn, "success")
        assert precision_snapshot(conn).sufficient_sample is False

        _seed_retrieval(conn, "failed")  # 30th resolved row
        assert precision_snapshot(conn).sufficient_sample is True

    def test_respects_lookback_window(self, conn: sqlite3.Connection) -> None:
        _seed_retrieval(conn, "success", days_ago=0)
        _seed_retrieval(conn, "rework", days_ago=40)  # outside 30d
        snap = precision_snapshot(conn, lookback_days=30)
        assert snap.successes == 1
        assert snap.failures == 0
        assert snap.total_retrievals == 1


# ---------------------------------------------------------------------------
# should_enable_contextual_enrichment
# ---------------------------------------------------------------------------

class TestShouldEnable:
    def test_pre_v10_returns_no_signal(self, tmp_path: Path) -> None:
        raw = sqlite3.connect(str(tmp_path / "raw.db"))
        try:
            enable, reason, snap = should_enable_contextual_enrichment(raw)
            assert enable is False
            assert "pre_v10" in reason
            assert snap["precision"] == 0.0
        finally:
            raw.close()

    def test_no_resolved_yet(self, conn: sqlite3.Connection) -> None:
        _seed_retrieval(conn, None)
        enable, reason, _ = should_enable_contextual_enrichment(conn)
        assert enable is False
        assert "no_resolved" in reason

    def test_insufficient_sample(self, conn: sqlite3.Connection) -> None:
        for _ in range(5):
            _seed_retrieval(conn, "rework")
        enable, reason, snap = should_enable_contextual_enrichment(conn)
        assert enable is False
        assert "insufficient_sample" in reason
        assert snap["sufficient_sample"] is False

    def test_precision_above_target(self, conn: sqlite3.Connection) -> None:
        # 30 resolved, 28 success (precision 93%) → above target
        for _ in range(28):
            _seed_retrieval(conn, "success")
        for _ in range(2):
            _seed_retrieval(conn, "rework")
        enable, reason, snap = should_enable_contextual_enrichment(conn)
        assert enable is False
        assert "precision" in reason
        assert snap["precision"] >= PRECISION_TARGET

    def test_precision_below_target_enables(self, conn: sqlite3.Connection) -> None:
        # 30 resolved, 15 success (50%) → below 70%
        for _ in range(15):
            _seed_retrieval(conn, "success")
        for _ in range(15):
            _seed_retrieval(conn, "rework")
        enable, reason, snap = should_enable_contextual_enrichment(conn)
        assert enable is True
        assert "precision 0.50 < target" in reason
        assert snap["precision"] < PRECISION_TARGET

    def test_custom_threshold_override(self, conn: sqlite3.Connection) -> None:
        # 30 resolved, 20 success (67%) — default target fails, but with
        # target=0.60 it should NOT enable.
        for _ in range(20):
            _seed_retrieval(conn, "success")
        for _ in range(10):
            _seed_retrieval(conn, "rework")
        enable_default, _, _ = should_enable_contextual_enrichment(conn, target=0.70)
        assert enable_default is True
        enable_lower, _, _ = should_enable_contextual_enrichment(conn, target=0.60)
        assert enable_lower is False


# ---------------------------------------------------------------------------
# contextual_enrichment_stub
# ---------------------------------------------------------------------------

class TestContextualStub:
    def test_returns_same_content(self) -> None:
        out = contextual_enrichment_stub("A > B", "original body", doc_title="T")
        assert out["enriched_content"] == "original body"
        assert out["model"] is None
        assert out["would_enrich"] is True
        assert out["heading_path"] == "A > B"
        assert out["doc_title"] == "T"

    def test_no_side_effects(self) -> None:
        content = "unchanged"
        out = contextual_enrichment_stub("h", content)
        assert out["enriched_content"] is content  # same object, pure passthrough
        assert out["reason"] == "stub_only_no_llm_call"

    def test_handles_empty_inputs(self) -> None:
        out = contextual_enrichment_stub("", "")
        assert out["enriched_content"] == ""
        assert out["would_enrich"] is True  # stub always reports True


# ---------------------------------------------------------------------------
# Contract invariants
# ---------------------------------------------------------------------------

class TestInvariants:
    def test_constants_are_sane(self) -> None:
        assert 0.0 < PRECISION_TARGET <= 1.0
        assert MIN_SAMPLE_FOR_DECISION >= 1

    def test_snapshot_dict_keys_match_dataclass(self, conn: sqlite3.Connection) -> None:
        snap = precision_snapshot(conn)
        _, _, snap_d = should_enable_contextual_enrichment(conn)
        assert set(snap_d.keys()) == set(snap.__dict__.keys())
