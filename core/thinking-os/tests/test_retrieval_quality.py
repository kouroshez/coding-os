"""
Tests for retrieval_quality.py — Phase G.11 precision tracker + enrichment gate.

Covers:
  - migration v11: retrieval_quality table + contextual_prefix/context_model cols
  - record_quality_signal clamps precision, survives pre-v11 DBs
  - backfill_quality_from_outcomes derives correct precision from (cited, outcome)
  - precision_summary returns mean/None based on _MIN_SAMPLE gate
  - should_enable_enrichment respects _MIN_SAMPLE and PRECISION_GATE
  - enrich_chunk_context_stub is a safe no-op placeholder
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db import init_db  # noqa: E402
from retrieval_quality import (  # noqa: E402
    PRECISION_GATE,
    _MIN_SAMPLE,
    backfill_quality_from_outcomes,
    enrich_chunk_context_stub,
    precision_summary,
    record_quality_signal,
    should_enable_enrichment,
)
from tools.retrieve import cite_retrievals, log_retrieval  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def conn(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> sqlite3.Connection:
    state = tmp_path / ".coding-os"
    state.mkdir()
    (state / "session-id").write_text("ses-g11")
    (state / ".task-current").write_text("TASK-G11")
    monkeypatch.setenv("COS_STATE_DIR", str(state))

    c = init_db(tmp_path / "test.db")
    yield c
    c.close()


@pytest.fixture
def chunk_ids(conn: sqlite3.Connection) -> list[int]:
    ids = []
    for i in range(3):
        cur = conn.execute(
            "INSERT INTO document_chunks "
            "(source_path, source_type, chunk_index, heading_path, "
            " content, content_hash, priority, mtime) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (f"docs/x{i}.md", "engineering", 0, "H1", f"body{i}",
             f"hash{i}", 0.5, 1000),
        )
        ids.append(cur.lastrowid)
    conn.commit()
    return ids


def _log_and_outcome(
    conn: sqlite3.Connection,
    chunk_id: int,
    *,
    cited: bool,
    outcome: str,
    task_id: str = "TASK-G11",
) -> int:
    rows = [{"id": chunk_id, "source_table": "document_chunks"}]
    rid = log_retrieval(conn, layer="docs", query="q",
                       rows=rows, task_id=task_id)[0]
    if cited:
        cite_retrievals(conn, [rid])
    conn.execute(
        "UPDATE retrievals SET outcome = ?, outcome_at = CURRENT_TIMESTAMP "
        "WHERE id = ?",
        (outcome, rid),
    )
    conn.commit()
    return rid


# ---------------------------------------------------------------------------
# Migration v11 shape
# ---------------------------------------------------------------------------

class TestMigrationV11:
    def test_retrieval_quality_columns(self, conn: sqlite3.Connection) -> None:
        cols = {
            row[1]
            for row in conn.execute("PRAGMA table_info(retrieval_quality)").fetchall()
        }
        expected = {"id", "retrieval_id", "task_id", "layer", "query",
                    "precision", "signal_source", "created_at"}
        assert expected <= cols

    def test_document_chunks_has_contextual_columns(
        self, conn: sqlite3.Connection,
    ) -> None:
        cols = {
            row[1]
            for row in conn.execute("PRAGMA table_info(document_chunks)").fetchall()
        }
        assert "contextual_prefix" in cols
        assert "context_model" in cols


# ---------------------------------------------------------------------------
# record_quality_signal
# ---------------------------------------------------------------------------

class TestRecordQualitySignal:
    def test_inserts_row(self, conn: sqlite3.Connection) -> None:
        rid = record_quality_signal(
            conn, retrieval_id=1, task_id="T1", layer="docs",
            query="q", precision=0.75, signal_source="test",
        )
        assert rid is not None
        row = conn.execute(
            "SELECT precision, signal_source FROM retrieval_quality WHERE id = ?",
            (rid,),
        ).fetchone()
        assert abs(row["precision"] - 0.75) < 1e-9
        assert row["signal_source"] == "test"

    def test_clamps_high_precision(self, conn: sqlite3.Connection) -> None:
        rid = record_quality_signal(
            conn, retrieval_id=1, task_id="T1", layer="docs",
            query="q", precision=2.0, signal_source="test",
        )
        precision = conn.execute(
            "SELECT precision FROM retrieval_quality WHERE id = ?", (rid,),
        ).fetchone()[0]
        assert precision == 1.0

    def test_clamps_low_precision(self, conn: sqlite3.Connection) -> None:
        rid = record_quality_signal(
            conn, retrieval_id=1, task_id="T1", layer="docs",
            query="q", precision=-0.5, signal_source="test",
        )
        precision = conn.execute(
            "SELECT precision FROM retrieval_quality WHERE id = ?", (rid,),
        ).fetchone()[0]
        assert precision == 0.0

    def test_returns_none_on_pre_v11(self, tmp_path: Path) -> None:
        raw = sqlite3.connect(str(tmp_path / "raw.db"))
        try:
            assert record_quality_signal(
                raw, retrieval_id=1, task_id=None, layer="docs",
                query=None, precision=0.5, signal_source="test",
            ) is None
        finally:
            raw.close()


# ---------------------------------------------------------------------------
# backfill_quality_from_outcomes
# ---------------------------------------------------------------------------

class TestBackfill:
    def test_cited_success_maps_to_1(
        self, conn: sqlite3.Connection, chunk_ids: list[int],
    ) -> None:
        _log_and_outcome(conn, chunk_ids[0], cited=True, outcome="success")
        result = backfill_quality_from_outcomes(conn)
        assert result["added"] == 1
        precision = conn.execute(
            "SELECT precision FROM retrieval_quality ORDER BY id DESC LIMIT 1"
        ).fetchone()[0]
        assert precision == 1.0

    def test_cited_rework_maps_to_0(
        self, conn: sqlite3.Connection, chunk_ids: list[int],
    ) -> None:
        _log_and_outcome(conn, chunk_ids[0], cited=True, outcome="rework")
        backfill_quality_from_outcomes(conn)
        precision = conn.execute(
            "SELECT precision FROM retrieval_quality ORDER BY id DESC LIMIT 1"
        ).fetchone()[0]
        assert precision == 0.0

    def test_passive_success_neutral(
        self, conn: sqlite3.Connection, chunk_ids: list[int],
    ) -> None:
        _log_and_outcome(conn, chunk_ids[0], cited=False, outcome="success")
        backfill_quality_from_outcomes(conn)
        precision = conn.execute(
            "SELECT precision FROM retrieval_quality ORDER BY id DESC LIMIT 1"
        ).fetchone()[0]
        assert precision == 0.5

    def test_idempotent(
        self, conn: sqlite3.Connection, chunk_ids: list[int],
    ) -> None:
        _log_and_outcome(conn, chunk_ids[0], cited=True, outcome="success")
        r1 = backfill_quality_from_outcomes(conn)
        r2 = backfill_quality_from_outcomes(conn)
        assert r1["added"] == 1
        assert r2["added"] == 0

    def test_no_op_on_pre_v11(self, tmp_path: Path) -> None:
        raw = sqlite3.connect(str(tmp_path / "raw.db"))
        try:
            result = backfill_quality_from_outcomes(raw)
            assert result["status"] == "pre_v11_no_op"
        finally:
            raw.close()


# ---------------------------------------------------------------------------
# precision_summary
# ---------------------------------------------------------------------------

class TestPrecisionSummary:
    def test_insufficient_data_status_and_not_actionable(
        self, conn: sqlite3.Connection,
    ) -> None:
        """Under _MIN_SAMPLE: mean is reported (fact) but below_gate stays
        False (no decision) and status flags the small sample."""
        for i in range(5):
            record_quality_signal(
                conn, retrieval_id=i, task_id="T", layer="docs",
                query="q", precision=0.9, signal_source="test",
            )
        summary = precision_summary(conn)
        assert summary["status"] == "insufficient_data"
        assert summary["samples"] == 5
        assert summary["mean_precision"] == 0.9  # factual report even with small n
        assert summary["below_gate"] is False   # NEVER actionable with small n

    def test_high_precision_not_below_gate(
        self, conn: sqlite3.Connection,
    ) -> None:
        for i in range(_MIN_SAMPLE + 5):
            record_quality_signal(
                conn, retrieval_id=i, task_id="T", layer="docs",
                query="q", precision=0.9, signal_source="test",
            )
        summary = precision_summary(conn)
        assert summary["status"] == "ok"
        assert summary["mean_precision"] == 0.9
        assert summary["below_gate"] is False

    def test_low_precision_triggers_below_gate(
        self, conn: sqlite3.Connection,
    ) -> None:
        for i in range(_MIN_SAMPLE + 5):
            record_quality_signal(
                conn, retrieval_id=i, task_id="T", layer="docs",
                query="q", precision=0.4, signal_source="test",
            )
        summary = precision_summary(conn)
        assert summary["status"] == "ok"
        assert summary["mean_precision"] < PRECISION_GATE
        assert summary["below_gate"] is True

    def test_layer_filter(self, conn: sqlite3.Connection) -> None:
        for i in range(_MIN_SAMPLE):
            record_quality_signal(
                conn, retrieval_id=i, task_id="T", layer="docs",
                query="q", precision=0.9, signal_source="test",
            )
        for i in range(_MIN_SAMPLE, _MIN_SAMPLE + 10):
            record_quality_signal(
                conn, retrieval_id=i, task_id="T", layer="tasks",
                query="q", precision=0.3, signal_source="test",
            )
        docs_summary = precision_summary(conn, layer="docs")
        tasks_summary = precision_summary(conn, layer="tasks")
        assert docs_summary["mean_precision"] == 0.9
        assert docs_summary["below_gate"] is False
        # tasks has 10 samples — below _MIN_SAMPLE → insufficient_data
        assert tasks_summary["status"] == "insufficient_data"


# ---------------------------------------------------------------------------
# should_enable_enrichment
# ---------------------------------------------------------------------------

class TestEnableEnrichment:
    def test_declines_when_insufficient_data(
        self, conn: sqlite3.Connection,
    ) -> None:
        result = should_enable_enrichment(conn)
        assert result["recommend"] is False
        assert "insufficient_data" in result["reason"]

    def test_declines_when_precision_ok(
        self, conn: sqlite3.Connection,
    ) -> None:
        for i in range(_MIN_SAMPLE + 5):
            record_quality_signal(
                conn, retrieval_id=i, task_id="T", layer="docs",
                query="q", precision=0.85, signal_source="test",
            )
        result = should_enable_enrichment(conn)
        assert result["recommend"] is False
        assert "no enrichment needed" in result["reason"]

    def test_recommends_when_below_gate(
        self, conn: sqlite3.Connection,
    ) -> None:
        for i in range(_MIN_SAMPLE + 5):
            record_quality_signal(
                conn, retrieval_id=i, task_id="T", layer="docs",
                query="q", precision=0.45, signal_source="test",
            )
        result = should_enable_enrichment(conn)
        assert result["recommend"] is True
        assert "below gate" in result["reason"]
        assert "cost_warning" in result
        assert "NOT YET IMPLEMENTED" in result["cost_warning"]


# ---------------------------------------------------------------------------
# enrich_chunk_context_stub
# ---------------------------------------------------------------------------

class TestEnrichmentStub:
    def test_returns_stub_shape(self) -> None:
        out = enrich_chunk_context_stub({"content": "x", "heading_path": "H1 > H2"})
        assert out == {
            "contextual_prefix": None,
            "context_model": None,
            "status": "stub",
        }

    def test_is_pure(self) -> None:
        """Calling the stub twice must return the same result (no side effects)."""
        a = enrich_chunk_context_stub({"content": "x"})
        b = enrich_chunk_context_stub({"content": "x"})
        assert a == b
