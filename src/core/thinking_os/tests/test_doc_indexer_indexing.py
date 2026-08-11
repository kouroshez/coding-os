"""
Tests for core/thinking_os/doc_indexer.py — document RAG.

Covers:
  - chunk_markdown: H2/H3 splitting, front-matter stripping, oversized chunks,
    heading_path construction, content_hash determinism
  - load_rag_config: parses yaml, validates schema, missing file
  - walk_sources: respects path/exclude, only matches *.md, follows nested dirs
  - index_docs: end-to-end on a temp project, mtime skip, force re-index,
    orphan cleanup, embedding side effect
"""

from __future__ import annotations

import os
import sqlite3
import sys
import time
from pathlib import Path

import pytest

# Make doc_indexer + db importable from the package root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import embeddings
from database import init_db
from doc_indexer import (
    index_docs,
)

REQUIRES_RAG = pytest.mark.skipif(
    not embeddings.is_available(),
    reason="sentence-transformers + numpy not installed (uv sync --extra rag)",
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_db(tmp_path: Path) -> sqlite3.Connection:
    conn = init_db(tmp_path / "test.db")
    yield conn
    conn.close()


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """Create a minimal docs/ tree for indexer tests."""
    project = tmp_path / "project"
    docs = project / "docs"
    (docs / "PRD").mkdir(parents=True)
    (docs / "architecture" / "adr").mkdir(parents=True)
    (docs / "engineering").mkdir(parents=True)
    (docs / "playbooks").mkdir(parents=True)

    (docs / "PRD" / "01-vision.md").write_text(
        "<!-- domain:PRODUCT | layer:spec | ssot:true | updated:2026-04-06 -->\n"
        "# Vision\n"
        "\n"
        "## Goals\n"
        "Build a great product.\n"
        "\n"
        "## Non-goals\n"
        "Boil the ocean.\n",
        encoding="utf-8",
    )

    (docs / "architecture" / "01-stack.md").write_text(
        "<!-- domain:ARCH | layer:spec | ssot:true | updated:2026-04-06 -->\n"
        "# Stack\n"
        "\n"
        "## Backend\n"
        "Django + DRF.\n"
        "\n"
        "## Frontend\n"
        "Next.js + React.\n",
        encoding="utf-8",
    )

    (docs / "architecture" / "adr" / "ADR-001-django.md").write_text(
        "<!-- domain:ARCH | layer:adr | ssot:true | updated:2026-04-06 -->\n"
        "# ADR-001: Use Django\n"
        "\n"
        "## Decision\n"
        "We chose Django because of mature ecosystem.\n",
        encoding="utf-8",
    )

    (docs / "engineering" / "backend-rules.md").write_text(
        "<!-- domain:BACKEND | layer:policy | ssot:true | updated:2026-04-06 -->\n"
        "# Backend Rules\n"
        "\n"
        "## Error Handling\n"
        "Always raise typed exceptions.\n",
        encoding="utf-8",
    )

    # Playbook should be excluded
    (docs / "playbooks" / "backend-api.md").write_text(
        "<!-- domain:ALL | layer:playbook | ssot:true | updated:2026-04-06 -->\n"
        "# Backend Playbook\n"
        "Should never be indexed.\n",
        encoding="utf-8",
    )

    return project


@pytest.fixture
def tmp_config(tmp_project: Path) -> Path:
    """Write a minimal rag-config.yaml for the temp project."""
    state = tmp_project / ".coding-os"
    state.mkdir()
    config = state / "rag-config.yaml"
    config.write_text(
        """
sources:
  - path: docs/PRD/
    type: prd
  - path: docs/architecture/
    type: architecture
    exclude:
      - adr/
  - path: docs/architecture/adr/
    type: adr
  - path: docs/engineering/
    type: engineering
    priority: 0.7

exclude:
  - docs/playbooks/
""",
        encoding="utf-8",
    )
    return config


# ---------------------------------------------------------------------------
# Front-matter / heading helpers
# ---------------------------------------------------------------------------


class TestIndexDocs:
    def test_first_run_indexes_files(
        self, tmp_db: sqlite3.Connection, tmp_project: Path, tmp_config: Path
    ) -> None:
        stats = index_docs(tmp_db, tmp_config, tmp_project)
        assert stats["processed"] >= 4
        assert stats["new_chunks"] >= 4
        assert stats["updated_files"] >= 4
        # Verify rows are in document_chunks
        count = tmp_db.execute("SELECT COUNT(*) FROM document_chunks").fetchone()[0]
        assert count >= 4

    def test_counts_missing_frontmatter(
        self, tmp_db: sqlite3.Connection, tmp_project: Path, tmp_config: Path
    ) -> None:
        # TASK-124 (D3-F7): a body without a parseable <!-- domain --> header is
        # a Stage-1 metadata gap and must surface in the index summary, not just
        # a silent logger.debug.
        (tmp_project / "docs" / "engineering" / "no-frontmatter.md").write_text(
            "# No Header\n\nplain body, no domain comment\n", encoding="utf-8"
        )
        stats = index_docs(tmp_db, tmp_config, tmp_project)
        assert "missing_frontmatter" in stats
        assert stats["missing_frontmatter"] >= 1

    def test_superseded_doc_indexed_inactive(
        self, tmp_db: sqlite3.Connection, tmp_project: Path, tmp_config: Path
    ) -> None:
        # D7-F9 (TASK-138): a doc with superseded_by in its header indexes
        # is_active=0 so cos_doc_search hides the past era by default; a normal
        # doc stays is_active=1.
        eng = tmp_project / "docs" / "engineering"
        (eng / "old-era.md").write_text(
            "<!-- domain:CORE | layer:engineering | ssot:false | updated:2026-01-01 | "
            "superseded_by:docs/engineering/new-era.md -->\n# Old Era\n\nsuperseded\n",
            encoding="utf-8",
        )
        (eng / "new-era.md").write_text(
            "<!-- domain:CORE | layer:engineering | ssot:true | updated:2026-06-01 -->\n"
            "# New Era\n\ncurrent\n",
            encoding="utf-8",
        )
        index_docs(tmp_db, tmp_config, tmp_project)
        old = [
            r[0]
            for r in tmp_db.execute(
                "SELECT DISTINCT is_active FROM document_chunks WHERE source_path LIKE '%old-era.md'"
            ).fetchall()
        ]
        new = [
            r[0]
            for r in tmp_db.execute(
                "SELECT DISTINCT is_active FROM document_chunks WHERE source_path LIKE '%new-era.md'"
            ).fetchall()
        ]
        assert old == [0]  # superseded → inactive
        assert new == [1]  # current → active

    def test_playbook_not_indexed(
        self, tmp_db: sqlite3.Connection, tmp_project: Path, tmp_config: Path
    ) -> None:
        index_docs(tmp_db, tmp_config, tmp_project)
        playbook_rows = tmp_db.execute(
            "SELECT COUNT(*) FROM document_chunks WHERE source_path LIKE '%playbooks%'"
        ).fetchone()[0]
        assert playbook_rows == 0

    def test_source_type_recorded(
        self, tmp_db: sqlite3.Connection, tmp_project: Path, tmp_config: Path
    ) -> None:
        index_docs(tmp_db, tmp_config, tmp_project)
        types = {
            row[0]
            for row in tmp_db.execute("SELECT DISTINCT source_type FROM document_chunks").fetchall()
        }
        assert "prd" in types
        assert "architecture" in types
        assert "adr" in types
        assert "engineering" in types

    def test_priority_recorded(
        self, tmp_db: sqlite3.Connection, tmp_project: Path, tmp_config: Path
    ) -> None:
        index_docs(tmp_db, tmp_config, tmp_project)
        eng_priority = tmp_db.execute(
            "SELECT priority FROM document_chunks WHERE source_type = 'engineering' LIMIT 1"
        ).fetchone()[0]
        assert eng_priority == pytest.approx(0.7)

    def test_unchanged_file_skipped_on_second_run(
        self, tmp_db: sqlite3.Connection, tmp_project: Path, tmp_config: Path
    ) -> None:
        first = index_docs(tmp_db, tmp_config, tmp_project)
        # Second run with no file changes should skip every file
        second = index_docs(tmp_db, tmp_config, tmp_project)
        assert second["skipped"] == first["processed"]
        assert second["updated_files"] == 0

    def test_changed_file_re_indexed(
        self, tmp_db: sqlite3.Connection, tmp_project: Path, tmp_config: Path
    ) -> None:
        index_docs(tmp_db, tmp_config, tmp_project)
        # Modify a file and bump its mtime
        target = tmp_project / "docs" / "PRD" / "01-vision.md"
        target.write_text(
            "<!-- domain:PRODUCT | layer:spec | ssot:true | updated:2026-04-07 -->\n"
            "# Vision Updated\n"
            "\n"
            "## Goals\n"
            "Brand new goals.\n",
            encoding="utf-8",
        )
        # Bump mtime to ensure detection works even on fast filesystems
        future = int(time.time()) + 60
        os.utime(target, (future, future))

        second = index_docs(tmp_db, tmp_config, tmp_project)
        assert second["updated_files"] == 1
        # Old chunks for that file are gone, new ones present
        new_content_rows = tmp_db.execute(
            "SELECT content FROM document_chunks WHERE source_path = 'docs/PRD/01-vision.md'"
        ).fetchall()
        new_text = " ".join(r[0] for r in new_content_rows)
        assert "Brand new goals" in new_text

    def test_force_reindexes_unchanged(
        self, tmp_db: sqlite3.Connection, tmp_project: Path, tmp_config: Path
    ) -> None:
        index_docs(tmp_db, tmp_config, tmp_project)
        forced = index_docs(tmp_db, tmp_config, tmp_project, force=True)
        # Force should re-index every file (no skips)
        assert forced["skipped"] == 0
        assert forced["updated_files"] == forced["processed"]

    def test_orphaned_chunks_deleted(
        self, tmp_db: sqlite3.Connection, tmp_project: Path, tmp_config: Path
    ) -> None:
        index_docs(tmp_db, tmp_config, tmp_project)
        # Delete a source file
        (tmp_project / "docs" / "PRD" / "01-vision.md").unlink()
        second = index_docs(tmp_db, tmp_config, tmp_project)
        assert second["deleted_files"] >= 1
        # No chunks remain for the deleted file
        rows = tmp_db.execute(
            "SELECT COUNT(*) FROM document_chunks WHERE source_path = 'docs/PRD/01-vision.md'"
        ).fetchone()[0]
        assert rows == 0

    @REQUIRES_RAG
    def test_index_creates_embeddings(
        self, tmp_db: sqlite3.Connection, tmp_project: Path, tmp_config: Path
    ) -> None:
        index_docs(tmp_db, tmp_config, tmp_project)
        embedding_count = tmp_db.execute(
            "SELECT COUNT(*) FROM embeddings WHERE source_table = 'document_chunks'"
        ).fetchone()[0]
        chunk_count = tmp_db.execute("SELECT COUNT(*) FROM document_chunks").fetchone()[0]
        assert embedding_count == chunk_count
        assert embedding_count > 0

    @REQUIRES_RAG
    def test_search_finds_indexed_chunk(
        self, tmp_db: sqlite3.Connection, tmp_project: Path, tmp_config: Path
    ) -> None:
        """End-to-end: index + semantic search across document_chunks."""
        index_docs(tmp_db, tmp_config, tmp_project)
        results = embeddings.search_similar(
            tmp_db,
            "django web framework",
            source_tables=["document_chunks"],
            limit=5,
            threshold=0.05,
        )
        assert len(results) >= 1
        # Top result should reference the architecture/Django doc
        top_id = results[0]["source_id"]
        row = tmp_db.execute(
            "SELECT source_path, content FROM document_chunks WHERE id = ?",
            (top_id,),
        ).fetchone()
        assert row is not None
        assert "django" in row[1].lower() or "Django" in row[1]


class TestPathResolutionRegression:
    """Regression guard for the bug caught during end-to-end
    verification: on macOS `/tmp` is a symlink to `/private/tmp`, so
    `Path('/tmp/x').relative_to(Path('/private/tmp/x'))` raises ValueError.

    `index_docs` must resolve both the project_root argument and every
    walked file path before taking the relative path, so callers can pass
    either the symlinked or the resolved form without crashing.
    """

    def test_symlinked_project_root_accepted(
        self, tmp_db: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """Pass a symlink-parent path as project_root — index_docs should
        normalize internally and succeed even if the walker sees resolved
        absolute paths."""
        # Build a minimal project in tmp_path (real location)
        project = tmp_path / "project"
        docs = project / "docs" / "PRD"
        docs.mkdir(parents=True)
        (docs / "01-vision.md").write_text(
            "<!-- domain:PRODUCT | layer:spec | ssot:true | updated:2026-04-06 -->\n"
            "# Vision\n\n## Goals\nBuild something.\n",
            encoding="utf-8",
        )
        state = project / ".coding-os"
        state.mkdir()
        (state / "rag-config.yaml").write_text(
            "sources:\n  - path: docs/PRD/\n    type: prd\nexclude: []\n",
            encoding="utf-8",
        )

        # Create a symlink to the project and pass THAT to index_docs.
        # Emulates the macOS `/tmp` vs `/private/tmp` situation where a
        # caller might pass one form and the walker returns the other.
        link_parent = tmp_path / "link-to-project"
        link_parent.symlink_to(project, target_is_directory=True)

        stats = index_docs(
            tmp_db,
            link_parent / ".coding-os" / "rag-config.yaml",
            link_parent,
        )

        # Should succeed without raising ValueError
        assert stats["errors"] == 0
        assert stats["new_chunks"] >= 1

        # Verify stored source_path is relative (not absolute)
        row = tmp_db.execute("SELECT source_path FROM document_chunks LIMIT 1").fetchone()
        assert row is not None
        assert not row[0].startswith("/"), f"expected relative path, got {row[0]!r}"
