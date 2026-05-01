"""V1 file-level incremental indexing tests (graph_os V1).

PURPOSE: Exercise the ``file_index_state`` cache added in migration v17
         and wired into ``reindex_dispatch.dispatch``. These tests
         guarantee the short-circuit actually fires on unchanged
         content, and that mutation / failure / force paths behave.
INPUT:   tmp_path SQLite DB + throwaway project layout.
OUTPUT:  pytest assertions.
DEPENDS: graph_os.tools.reindex_dispatch.dispatch, coding-os.db.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest


def _write(p: Path, text: str) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


@pytest.fixture()
def project(tmp_path):
    (tmp_path / ".coding-os").mkdir()
    (tmp_path / ".coding-os" / "rag-config.yaml").write_text(
        "sources:\n  - glob: 'docs/**/*.md'\n    category: docs\n",
        encoding="utf-8",
    )
    (tmp_path / "docs").mkdir()
    (tmp_path / "core").mkdir()
    return tmp_path


def _state_rows(db_path: Path) -> list[dict]:
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT file_path, content_hash, extractor_chain, "
            "nodes_written, edges_written, parse_errors_count, "
            "last_indexed_at, last_error FROM file_index_state"
        ).fetchall()
    finally:
        conn.close()
    keys = [
        "file_path",
        "content_hash",
        "extractor_chain",
        "nodes_written",
        "edges_written",
        "parse_errors_count",
        "last_indexed_at",
        "last_error",
    ]
    return [dict(zip(keys, r)) for r in rows]


class TestIncrementalCache:
    def test_first_index_writes_state(self, project, tmp_path):
        src = _write(project / "core" / "foo.py", "def hello(x):\n    return x\n")
        from graph_os.tools.reindex_dispatch import dispatch

        db = tmp_path / "test.db"
        report = dispatch(src, project_root=project, db_path=str(db))
        assert report["status"] == "ok"
        assert report["cache"] == "miss"
        assert report["layers"]["graph"]["status"] == "ok"

        rows = _state_rows(db)
        assert len(rows) == 1
        row = rows[0]
        assert row["file_path"] == "core/foo.py"
        assert row["content_hash"] and len(row["content_hash"]) == 64
        assert row["extractor_chain"] == "code_python,contracts"
        assert row["nodes_written"] >= 1
        assert row["last_error"] is None

    def test_unchanged_skips(self, project, tmp_path):
        src = _write(project / "core" / "foo.py", "def hello(x):\n    return x\n")
        from graph_os.tools.reindex_dispatch import dispatch

        db = tmp_path / "test.db"
        first = dispatch(src, project_root=project, db_path=str(db))
        assert first["cache"] == "miss"
        first_nodes = first["layers"]["graph"]["nodes_written"]
        first_edges = first["layers"]["graph"]["edges_written"]

        second = dispatch(src, project_root=project, db_path=str(db))
        assert second["cache"] == "hit"
        g2 = second["layers"]["graph"]
        assert g2["status"] == "skipped"
        assert g2["reason"] == "unchanged"
        assert g2["nodes_written"] == first_nodes
        assert g2["edges_written"] == first_edges

    def test_modified_reindexes(self, project, tmp_path):
        src = _write(project / "core" / "foo.py", "def hello():\n    return 1\n")
        from graph_os.tools.reindex_dispatch import dispatch

        db = tmp_path / "test.db"
        first = dispatch(src, project_root=project, db_path=str(db))
        h1 = _state_rows(db)[0]["content_hash"]

        # Modify file content — new hash, extractor must re-run.
        src.write_text("def hello():\n    return 42\n", encoding="utf-8")

        second = dispatch(src, project_root=project, db_path=str(db))
        assert second["cache"] == "miss"
        assert second["layers"]["graph"]["status"] == "ok"

        h2 = _state_rows(db)[0]["content_hash"]
        assert h1 != h2

    def test_force_bypasses_cache(self, project, tmp_path):
        src = _write(project / "core" / "foo.py", "def hello():\n    return 1\n")
        from graph_os.tools.reindex_dispatch import dispatch

        db = tmp_path / "test.db"
        dispatch(src, project_root=project, db_path=str(db))

        forced = dispatch(src, project_root=project, db_path=str(db), force=True)
        assert forced["cache"] == "bypass"
        # Extractor path returns status=ok, NOT skipped — a cache hit
        # would return status=skipped.
        assert forced["layers"]["graph"]["status"] == "ok"

    def test_extractor_failure_marks_state(self, project, tmp_path, monkeypatch):
        src = _write(project / "core" / "foo.py", "def hello():\n    return 1\n")
        from graph_os.tools import reindex_dispatch

        db = tmp_path / "test.db"
        # First, success baseline — establishes the row with a real hash.
        reindex_dispatch.dispatch(src, project_root=project, db_path=str(db))
        baseline_hash = _state_rows(db)[0]["content_hash"]

        # Mutate file so next dispatch computes a new hash, then force
        # the extractor to raise.
        src.write_text("def hello():\n    return 999\n", encoding="utf-8")

        def _boom(*args, **kwargs):
            raise RuntimeError("extractor exploded")

        monkeypatch.setattr(reindex_dispatch, "_reindex_graph", _boom)

        report = reindex_dispatch.dispatch(src, project_root=project, db_path=str(db))
        assert report["layers"]["graph"]["status"] == "error"

        row = _state_rows(db)[0]
        assert row["last_error"] == "extractor exploded"
        # Hash NOT advanced — retry on next call stays possible.
        assert row["content_hash"] == baseline_hash

    def test_docs_md_path_uses_cache(self, project, tmp_path):
        src = _write(project / "docs" / "a.md", "# hello\n\nSee [b](./b.md).\n")
        from graph_os.tools.reindex_dispatch import dispatch

        db = tmp_path / "test.db"
        first_report = dispatch(src, project_root=project, db_path=str(db))
        assert first_report["cache"] == "miss"

        # The docs layer MAY be "unscoped" (no chunks matched) or "ok".
        # In either case a docs:md row should exist.
        rows = _state_rows(db)
        chains = {r["extractor_chain"] for r in rows}
        assert "docs:md" in chains

        second = dispatch(src, project_root=project, db_path=str(db))
        # Both docs + graph should short-circuit when both cached.
        assert second["layers"]["docs"].get("cache") == "hit"
        assert second["layers"]["graph"].get("cache") == "hit"
        assert second["cache"] == "hit"
