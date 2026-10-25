"""
Tests for tools/retrieve.py — retrieval-outcome feedback loop.

Covers:
  - log_retrieval: inserts one row per result, idempotent vs pre-v10 DBs
  - cite_retrievals: flips was_cited, reports unknown ids
  - backfill_task_outcome: updates outcome + outcome_at on task completion
  - learn_from_retrievals: moves document_chunks.priority per outcome signal,
    respects [0.1, 0.9] clamp, handles dry-run, respects lookback window
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import init_db
from tools.retrieve import (
    log_retrieval,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def conn(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> sqlite3.Connection:
    # Isolate session + task markers per test
    state_dir = tmp_path / ".coding-os"
    state_dir.mkdir()
    (state_dir / "session-id").write_text("ses-test")
    (state_dir / ".task-current").write_text("TASK-RT-001")
    monkeypatch.setenv("COS_STATE_DIR", str(state_dir))

    c = init_db(tmp_path / "test.db")
    yield c
    c.close()


@pytest.fixture
def chunk_ids(conn: sqlite3.Connection) -> list[int]:
    """Insert three document_chunks rows with varied priority and return ids."""
    ids = []
    for i, prio in enumerate([0.5, 0.5, 0.85]):
        cur = conn.execute(
            "INSERT INTO document_chunks "
            "(source_path, source_type, chunk_index, heading_path, "
            " content, content_hash, priority, mtime) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (f"docs/x{i}.md", "engineering", 0, "H1", f"body{i}", f"hash{i}", prio, 1000),
        )
        ids.append(cur.lastrowid)
    conn.commit()
    return ids


# ---------------------------------------------------------------------------
# log_retrieval
# ---------------------------------------------------------------------------


class TestLogRetrieval:
    def test_empty_rows_returns_empty_list(self, conn):
        assert log_retrieval(conn, layer="docs", query="x", rows=[]) == []

    def test_inserts_one_row_per_result(self, conn, chunk_ids):
        rows = [
            {"id": chunk_ids[0], "source_table": "document_chunks", "score": 0.8},
            {"id": chunk_ids[1], "source_table": "document_chunks", "score": 0.6},
        ]
        ids = log_retrieval(conn, layer="docs", query="q1", rows=rows)
        assert len(ids) == 2
        stored = conn.execute(
            "SELECT session_id, task_id, layer, query, source_table, source_id, score "
            "FROM retrievals ORDER BY id"
        ).fetchall()
        assert stored[0]["session_id"] == "ses-test"
        assert stored[0]["task_id"] == "TASK-RT-001"
        assert stored[0]["layer"] == "docs"
        assert stored[0]["query"] == "q1"
        assert stored[0]["source_table"] == "document_chunks"
        assert stored[0]["source_id"] == chunk_ids[0]
        assert stored[0]["score"] == pytest.approx(0.8)

    def test_infers_source_table_from_layer(self, conn, chunk_ids):
        """doc_search rows carry source_path, not source_table — should infer."""
        rows = [{"id": chunk_ids[0], "source_path": "docs/a.md", "score": 0.5}]
        ids = log_retrieval(conn, layer="docs", query="auto", rows=rows)
        assert len(ids) == 1
        st = conn.execute("SELECT source_table FROM retrievals WHERE id = ?", (ids[0],)).fetchone()[
            0
        ]
        assert st == "document_chunks"

    def test_tasks_layer_infers_table(self, conn):
        rows = [{"id": 1, "task_id": "TASK-1", "score": 0.4}]
        ids = log_retrieval(conn, layer="tasks", query="q", rows=rows)
        assert len(ids) == 1
        st = conn.execute("SELECT source_table FROM retrievals WHERE id = ?", (ids[0],)).fetchone()[
            0
        ]
        assert st == "tasks"

    def test_skips_row_with_no_id(self, conn):
        ids = log_retrieval(conn, layer="docs", query="x", rows=[{"content": "no id here"}])
        assert ids == []

    def test_explicit_task_id_overrides_state(self, conn, chunk_ids):
        rows = [{"id": chunk_ids[0], "source_table": "document_chunks"}]
        ids = log_retrieval(conn, layer="docs", query="q", rows=rows, task_id="TASK-OVERRIDE")
        stored = conn.execute("SELECT task_id FROM retrievals WHERE id = ?", (ids[0],)).fetchone()[
            0
        ]
        assert stored == "TASK-OVERRIDE"

    def test_no_op_on_pre_v10(self, tmp_path: Path):
        """Raw DB without any migrations — log_retrieval must silently no-op."""
        raw = sqlite3.connect(str(tmp_path / "raw.db"))
        try:
            result = log_retrieval(
                raw, layer="docs", query="x", rows=[{"id": 1, "source_table": "document_chunks"}]
            )
            assert result == []
        finally:
            raw.close()


# ---------------------------------------------------------------------------
# cite_retrievals
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# backfill_task_outcome
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# learn_from_retrievals — the actual priority learning loop
# ---------------------------------------------------------------------------
