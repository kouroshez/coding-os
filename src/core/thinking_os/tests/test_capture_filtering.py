"""
Tests for capture.py auto-observation hook (TASK-151, TASK-153).

Covers tool filtering, memory_type detection, impact scoring,
session_id fallback, DB-absent handling, and content hash dedup.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from capture import (
    _estimate_impact,
    _read_session_id,
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


class TestToolFiltering:
    def test_write_captured(self, db_path: Path) -> None:
        result = capture_observation(
            {"tool_name": "Write", "tool_input": {"file_path": "test.py"}},
            db_path=db_path,
        )
        assert result["status"] == "captured"

    def test_edit_captured(self, db_path: Path) -> None:
        result = capture_observation(
            {"tool_name": "Edit", "tool_input": {"file_path": "test.py"}},
            db_path=db_path,
        )
        assert result["status"] == "captured"

    def test_read_filtered(self, db_path: Path) -> None:
        result = capture_observation(
            {"tool_name": "Read", "tool_input": {"file_path": "test.py"}},
            db_path=db_path,
        )
        assert result["status"] == "filtered"

    def test_glob_filtered(self, db_path: Path) -> None:
        result = capture_observation(
            {"tool_name": "Glob", "tool_input": {"pattern": "*.py"}},
            db_path=db_path,
        )
        assert result["status"] == "filtered"

    def test_bash_filtered(self, db_path: Path) -> None:
        result = capture_observation(
            {"tool_name": "Bash", "tool_input": {"command": "ls"}},
            db_path=db_path,
        )
        assert result["status"] == "filtered"

    def test_no_file_path_skipped(self, db_path: Path) -> None:
        result = capture_observation(
            {"tool_name": "Write", "tool_input": {}},
            db_path=db_path,
        )
        assert result["status"] == "skipped"


class TestHotPathOutbox:
    def test_skip_embed_enqueues_outbox(self, db_path: Path, monkeypatch) -> None:
        # Wave 4: on the hot path the embed is deferred to the durable outbox
        # (no model load), not dropped. Plain INSERT — needs no rag deps.
        import sqlite3

        monkeypatch.setenv("COS_CAPTURE_SKIP_EMBED", "1")
        result = capture_observation(
            {"tool_name": "Write", "tool_input": {"file_path": "wave4_hotpath.py"}},
            db_path=db_path,
        )
        assert result["status"] == "captured"
        c = sqlite3.connect(db_path)
        n = c.execute("SELECT COUNT(*) FROM embedding_outbox").fetchone()[0]
        c.close()
        assert n == 1


class TestImpactScoring:
    def test_models_high_impact(self) -> None:
        score = _estimate_impact("backend/apps/products/models.py")
        assert score >= 0.7

    def test_migration_high_impact(self) -> None:
        score = _estimate_impact("backend/apps/products/migrations/0001.py")
        assert score >= 0.7

    def test_test_file_low_impact(self) -> None:
        score = _estimate_impact("tests/test_products.py")
        assert score <= 0.5

    def test_readme_low_impact(self) -> None:
        score = _estimate_impact("README.md")
        assert score <= 0.5

    def test_score_bounded(self) -> None:
        score = _estimate_impact("backend/apps/auth/security/models.py")
        assert 0.0 <= score <= 1.0


class TestSessionIdFallback:
    def test_fallback_format(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        # Neutralise agent-dir detection so we really exercise the fallback.
        monkeypatch.delenv("COS_AGENT_DIR", raising=False)
        monkeypatch.delenv("COS_AGENT", raising=False)
        sid = _read_session_id()
        assert sid.startswith("ses-anonymous-")

    def test_reads_session_file_from_agent_dir(self, tmp_path: Path, monkeypatch) -> None:
        """Session-id lives in the agent-private subdir now
        (docs/engineering/state-files.md). The resolver reads from
        $COS_AGENT_DIR/session-id when that env var is set."""
        monkeypatch.chdir(tmp_path)
        agent_dir = tmp_path / ".coding-os" / "claude"
        agent_dir.mkdir(parents=True)
        (agent_dir / "session-id").write_text("ses-claude-20260325-143022-a7b3")
        monkeypatch.setenv("COS_STATE_DIR", str(tmp_path / ".coding-os"))
        monkeypatch.setenv("COS_AGENT_DIR", str(agent_dir))
        monkeypatch.setenv("COS_AGENT", "claude")
        sid = _read_session_id()
        assert sid == "ses-claude-20260325-143022-a7b3"

    def test_reads_session_file_via_agent_marker(self, tmp_path: Path, monkeypatch) -> None:
        """When COS_AGENT_DIR isn't set explicitly, the resolver derives the
        agent from $COS_STATE_DIR/.agent (adapter install.sh writes this)."""
        monkeypatch.chdir(tmp_path)
        state_dir = tmp_path / ".coding-os"
        state_dir.mkdir()
        (state_dir / ".agent").write_text("codex")
        (state_dir / "codex").mkdir()
        (state_dir / "codex" / "session-id").write_text("ses-codex-20260325-143022-xyz1")
        monkeypatch.setenv("COS_STATE_DIR", str(state_dir))
        monkeypatch.delenv("COS_AGENT_DIR", raising=False)
        monkeypatch.delenv("COS_AGENT", raising=False)
        sid = _read_session_id()
        assert sid == "ses-codex-20260325-143022-xyz1"


class TestDbAbsent:
    def test_skip_if_db_absent(self, tmp_path: Path) -> None:
        result = capture_observation(
            {"tool_name": "Write", "tool_input": {"file_path": "test.py"}},
            db_path=tmp_path / "nonexistent.db",
        )
        assert result["status"] == "skipped"
        assert result["reason"] == "db_absent"
