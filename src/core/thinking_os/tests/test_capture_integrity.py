"""
Tests for capture.py auto-observation hook (TASK-151, TASK-153).

Covers tool filtering, memory_type detection, impact scoring,
session_id fallback, DB-absent handling, and content hash dedup.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from capture import (
    _compute_content_hash,
    capture_observation,
)
from database import init_db


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    p = tmp_path / "test.db"
    c = init_db(p)
    c.close()
    return p


import embeddings

REQUIRES_RAG = pytest.mark.skipif(
    not embeddings.is_available(),
    reason="sentence-transformers + numpy not installed (uv sync --extra rag)",
)


class TestDataIntegrity:
    def test_observation_fields(self, db_path: Path) -> None:
        capture_observation(
            {"tool_name": "Edit", "tool_input": {"file_path": "backend/apps/products/models.py"}},
            db_path=db_path,
        )
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM observations ORDER BY id DESC LIMIT 1").fetchone()
        conn.close()
        assert row is not None
        assert row["tool_name"] == "Edit"
        assert "models.py" in row["title"]
        assert row["files_modified"] == "backend/apps/products/models.py"
        assert row["memory_type"] == "changelog"
        assert row["impact_score"] >= 0.6
        assert row["cost_tokens"] > 0

    def test_title_uses_repo_relative_path(self, tmp_path: Path) -> None:
        # real <root>/.coding-os/coding-os.db layout so root derivation works
        root = tmp_path
        (root / ".coding-os").mkdir()
        db = root / ".coding-os" / "coding-os.db"
        init_db(db).close()
        abs_file = root / "src" / "core" / "thing.py"
        capture_observation(
            {"tool_name": "Edit", "tool_input": {"file_path": str(abs_file)}},
            db_path=db,
        )
        conn = sqlite3.connect(str(db))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT title FROM observations ORDER BY id DESC LIMIT 1").fetchone()
        conn.close()
        assert row["title"] == "Modified src/core/thing.py"
        assert str(root) not in row["title"]  # no absolute prefix / username leak

    def test_title_format_write(self, db_path: Path) -> None:
        capture_observation(
            {"tool_name": "Write", "tool_input": {"file_path": "new_file.py"}},
            db_path=db_path,
        )
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT title FROM observations ORDER BY id DESC LIMIT 1").fetchone()
        conn.close()
        assert row["title"].startswith("Created ")

    def test_title_format_edit(self, db_path: Path) -> None:
        capture_observation(
            {"tool_name": "Edit", "tool_input": {"file_path": "existing.py"}},
            db_path=db_path,
        )
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT title FROM observations ORDER BY id DESC LIMIT 1").fetchone()
        conn.close()
        assert row["title"].startswith("Modified ")


class TestContentHashDedup:
    def test_hash_deterministic(self) -> None:
        h1 = _compute_content_hash("Write", "test.py")
        h2 = _compute_content_hash("Write", "test.py")
        assert h1 == h2

    def test_hash_differs_for_different_files(self) -> None:
        h1 = _compute_content_hash("Write", "file_a.py")
        h2 = _compute_content_hash("Write", "file_b.py")
        assert h1 != h2

    def test_hash_differs_for_different_tools(self) -> None:
        h1 = _compute_content_hash("Write", "test.py")
        h2 = _compute_content_hash("Edit", "test.py")
        assert h1 != h2

    def test_duplicate_same_session_deduped(self, db_path: Path) -> None:
        data = {"tool_name": "Write", "tool_input": {"file_path": "dedup_test.py"}}
        r1 = capture_observation(data, db_path=db_path)
        r2 = capture_observation(data, db_path=db_path)
        r3 = capture_observation(data, db_path=db_path)
        assert r1["status"] == "captured"
        assert r2["status"] == "deduped"
        assert r3["status"] == "deduped"
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT memory_type FROM observations WHERE files_modified = ?",
            ("dedup_test.py",),
        ).fetchall()
        conn.close()
        assert len(rows) == 1
        assert rows[0]["memory_type"] == "changelog"

    def test_different_files_same_window_both_captured(self, db_path: Path) -> None:
        r1 = capture_observation(
            {"tool_name": "Write", "tool_input": {"file_path": "file_x.py"}},
            db_path=db_path,
        )
        r2 = capture_observation(
            {"tool_name": "Write", "tool_input": {"file_path": "file_y.py"}},
            db_path=db_path,
        )
        assert r1["status"] == "captured"
        assert r2["status"] == "captured"

    def test_content_hash_stored(self, db_path: Path) -> None:
        capture_observation(
            {"tool_name": "Write", "tool_input": {"file_path": "hash_test.py"}},
            db_path=db_path,
        )
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT content_hash FROM observations WHERE files_modified = 'hash_test.py'"
        ).fetchone()
        conn.close()
        assert row["content_hash"] is not None
        assert len(row["content_hash"]) == 16  # truncated SHA256


class TestCaptureEmbeddingIntegration:
    """Verify capture_observation creates a corresponding embeddings row."""

    @REQUIRES_RAG
    def test_capture_creates_embedding(self, db_path: Path) -> None:
        result = capture_observation(
            {
                "tool_name": "Edit",
                "tool_input": {"file_path": "backend/apps/auth/views.py"},
            },
            db_path=db_path,
        )
        assert result["status"] == "captured"
        obs_id = result["id"]

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT id, source_table, source_id FROM embeddings "
            "WHERE source_table = 'observations' AND source_id = ?",
            (obs_id,),
        ).fetchone()
        conn.close()
        assert row is not None, "expected embedding row for captured observation"
        assert row["source_table"] == "observations"
        assert row["source_id"] == obs_id

    def test_capture_succeeds_without_rag(self, db_path: Path, monkeypatch) -> None:
        """When embeddings unavailable, capture must still succeed cleanly."""
        # Mock is_available to False so the embedding step is a no-op
        monkeypatch.setattr(embeddings, "is_available", lambda: False)
        result = capture_observation(
            {"tool_name": "Edit", "tool_input": {"file_path": "test.py"}},
            db_path=db_path,
        )
        assert result["status"] == "captured"
