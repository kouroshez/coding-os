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


class TestChangelogRecallExclusion:
    def test_changelog_hidden_but_opt_in_visible(self, db_path: Path) -> None:
        from tools.memory import memory_search

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        conn.executemany(
            "INSERT INTO observations (session_id, tool_name, observation_type, "
            "memory_type, title, narrative, concepts) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                ("s", "Edit", "edit", "changelog", "Modified parser.py", "edit", "parser"),
                (
                    "s",
                    "Manual",
                    "discovery",
                    "discovery",
                    "Parser insight",
                    "why parser changed",
                    "parser",
                ),
            ],
        )
        conn.commit()

        hidden = memory_search(conn, query="parser", limit=10)
        types = {r.get("memory_type") for r in hidden["results"]}
        assert "changelog" not in types
        assert "discovery" in types

        opt_in = memory_search(conn, query="parser", limit=10, memory_type="changelog")
        assert opt_in["results"]
        assert all(r["memory_type"] == "changelog" for r in opt_in["results"])
        conn.close()


class TestExpiresAtStamp:
    def test_changelog_capture_stamps_ttl(self, db_path: Path) -> None:
        from datetime import datetime, timezone

        capture_observation({"tool_name": "Write", "tool_input": {"file_path": "svc.py"}}, db_path)
        c = init_db(db_path)
        row = c.execute(
            "SELECT memory_type, expires_at FROM observations ORDER BY id DESC LIMIT 1"
        ).fetchone()
        c.close()
        assert row[0] == "changelog"
        assert row[1] is not None  # a TTL was stamped
        exp = datetime.strptime(row[1], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        delta_days = (exp - datetime.now(timezone.utc)).days
        assert 28 <= delta_days <= 30  # ~30d changelog TTL
