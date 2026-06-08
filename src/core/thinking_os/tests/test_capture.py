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
    _detect_memory_type,
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


class TestMemoryTypeDetection:
    def test_backend(self) -> None:
        assert _detect_memory_type("backend/apps/products/models.py") == "pattern"

    def test_frontend(self) -> None:
        assert _detect_memory_type("frontend/src/components/Button.tsx") == "pattern"

    def test_docs(self) -> None:
        assert _detect_memory_type("docs/governance/agent-workflow.md") == "config"

    def test_claude_config(self) -> None:
        assert _detect_memory_type(".claude/settings.json") == "config"

    def test_infrastructure(self) -> None:
        assert _detect_memory_type("infrastructure/scripts/task-done.sh") == "workflow"

    def test_unknown_default(self) -> None:
        assert _detect_memory_type("random/file.txt") == "discovery"


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
        assert row["memory_type"] == "pattern"
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


# ---------------------------------------------------------------------------
# Content hash dedup
# ---------------------------------------------------------------------------


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

    def test_duplicate_within_30s_deduped(self, db_path: Path) -> None:
        data = {"tool_name": "Write", "tool_input": {"file_path": "dedup_test.py"}}
        r1 = capture_observation(data, db_path=db_path)
        r2 = capture_observation(data, db_path=db_path)
        assert r1["status"] == "captured"
        assert r2["status"] == "deduped"

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


# ---------------------------------------------------------------------------
# inline embedding side effects
# ---------------------------------------------------------------------------

import embeddings  # noqa: E402

REQUIRES_RAG = pytest.mark.skipif(
    not embeddings.is_available(),
    reason="sentence-transformers + numpy not installed (uv sync --extra rag)",
)


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


class TestScrubUsername:
    """files_modified must not leak the local OS username (memory.md § Privacy):
    in-repo → relative, $HOME → ~/, /tmp kept (no username, GC needs the prefix)."""

    def _db(self, tmp_path: Path) -> Path:
        db = tmp_path / ".coding-os" / "coding-os.db"
        db.parent.mkdir(parents=True)
        return db

    def test_in_repo_becomes_relative(self, tmp_path: Path) -> None:
        from capture import _scrub_username

        assert _scrub_username(str(tmp_path / "src" / "x.py"), self._db(tmp_path)) == "src/x.py"

    def test_home_outside_repo_becomes_tilde(self, tmp_path: Path) -> None:
        from capture import _scrub_username

        out = _scrub_username(str(Path.home() / "elsewhere" / "y.py"), self._db(tmp_path))
        assert out == "~/elsewhere/y.py"
        assert Path.home().name not in out  # username segment never leaks

    def test_tmp_path_kept_absolute(self, tmp_path: Path) -> None:
        from capture import _scrub_username

        assert _scrub_username("/tmp/foo.py", self._db(tmp_path)) == "/tmp/foo.py"

    def test_dash_encoded_username_scrubbed(self, tmp_path: Path) -> None:
        # ~/.claude/projects/-Users-<user>-… slug survives the ~/ rewrite — the
        # dash-encoded username must still be stripped (re-audit gap).
        from capture import _scrub_username

        dash = str(Path.home()).replace("/", "-")  # /Users/<u> -> -Users-<u>
        raw = f"{Path.home()}/.claude/projects/{dash}-Files-x/memory/MEMORY.md"
        out = _scrub_username(raw, self._db(tmp_path))
        assert Path.home().name not in out  # neither ~/ prefix nor dash slug leaks it
        assert out.startswith("~/.claude/projects/")

    def test_capture_stores_scrubbed_files_modified(self, tmp_path: Path) -> None:
        db = self._db(tmp_path)
        init_db(db)
        capture_observation(
            {"tool_name": "Edit", "tool_input": {"file_path": str(tmp_path / "src" / "z.py")}},
            db_path=db,
        )
        conn = sqlite3.connect(str(db))
        fm = conn.execute("SELECT files_modified FROM observations LIMIT 1").fetchone()[0]
        conn.close()
        assert fm == "src/z.py"  # not the absolute usernamed path


class TestTaskIdStamp:
    """capture stamps the active TASK-NNN onto the observation (post-v39) so
    per-task rework signals become derivable — the link a session-only key cannot
    give (a session spans many tasks)."""

    def test_read_current_task_parses_marker(self, tmp_path: Path, monkeypatch) -> None:
        from capture import _read_current_task

        panel = tmp_path / "panel"
        panel.mkdir()
        (panel / ".task-current").write_text("ses-abc-123 TASK-99")
        monkeypatch.setenv("COS_PANEL_DIR", str(panel))
        monkeypatch.delenv("COS_AGENT_DIR", raising=False)
        assert _read_current_task() == "TASK-99"

    def test_read_current_task_none_when_absent(self, tmp_path: Path, monkeypatch) -> None:
        from capture import _read_current_task

        empty = tmp_path / "empty"
        empty.mkdir()
        monkeypatch.setenv("COS_PANEL_DIR", str(empty))
        monkeypatch.delenv("COS_AGENT_DIR", raising=False)
        assert _read_current_task() is None

    def test_capture_stamps_active_task(self, tmp_path: Path, monkeypatch) -> None:
        db = tmp_path / ".coding-os" / "coding-os.db"
        db.parent.mkdir(parents=True)
        init_db(db)
        panel = tmp_path / "panel"
        panel.mkdir()
        (panel / ".task-current").write_text("ses-abc TASK-77")
        monkeypatch.setenv("COS_PANEL_DIR", str(panel))
        capture_observation(
            {"tool_name": "Edit", "tool_input": {"file_path": str(tmp_path / "src" / "z.py")}},
            db_path=db,
        )
        conn = sqlite3.connect(str(db))
        tid = conn.execute("SELECT task_id FROM observations LIMIT 1").fetchone()[0]
        conn.close()
        assert tid == "TASK-77"

    def test_capture_works_without_task_id_column(self, tmp_path: Path, monkeypatch) -> None:
        # Pre-v39 DBs lack observations.task_id; the dynamic-column INSERT must
        # still capture (the False branch of _observations_has_task_id).
        db = tmp_path / ".coding-os" / "coding-os.db"
        db.parent.mkdir(parents=True)
        init_db(db)
        drop = sqlite3.connect(str(db))
        drop.execute("ALTER TABLE observations DROP COLUMN task_id")  # simulate pre-v39
        drop.commit()
        drop.close()
        panel = tmp_path / "panel"
        panel.mkdir()
        (panel / ".task-current").write_text("ses TASK-5")
        monkeypatch.setenv("COS_PANEL_DIR", str(panel))
        capture_observation(
            {"tool_name": "Edit", "tool_input": {"file_path": str(tmp_path / "a.py")}},
            db_path=db,
        )
        conn = sqlite3.connect(str(db))
        count = conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
        conn.close()
        assert count == 1  # inserted despite the missing task_id column
