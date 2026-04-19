"""
Tests for core/thinking-os/doc_indexer.py — Phase B.3 document RAG.

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

import doc_indexer  # noqa: E402
import embeddings  # noqa: E402
from db import init_db  # noqa: E402
from doc_indexer import (  # noqa: E402
    DEFAULT_MAX_CHARS,
    chunk_markdown,
    index_docs,
    load_rag_config,
    walk_sources,
    _build_heading_path,
    _strip_front_matter,
    _extract_h1,
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

class TestHelpers:
    def test_strip_front_matter_removes_header(self) -> None:
        content = "<!-- domain:ALL | layer:spec | ssot:true | updated:2026-04-06 -->\n# Title\nbody"
        stripped = _strip_front_matter(content)
        assert "domain:ALL" not in stripped
        assert "# Title" in stripped

    def test_strip_front_matter_no_op_without_header(self) -> None:
        content = "# Title\nbody"
        assert _strip_front_matter(content) == content

    def test_extract_h1(self) -> None:
        assert _extract_h1("# Hello\n## Sub") == "Hello"

    def test_extract_h1_missing(self) -> None:
        assert _extract_h1("just text") == "Untitled"

    def test_build_heading_path_full(self) -> None:
        assert _build_heading_path("Doc", "Section", "Sub") == "Doc > Section > Sub"

    def test_build_heading_path_omits_empty(self) -> None:
        assert _build_heading_path("Doc", "Section", "") == "Doc > Section"
        assert _build_heading_path("Doc", "", "") == "Doc"


# ---------------------------------------------------------------------------
# chunk_markdown
# ---------------------------------------------------------------------------

class TestChunkMarkdown:
    def test_empty_input_returns_empty(self) -> None:
        assert chunk_markdown("") == []
        assert chunk_markdown("   ") == []

    def test_single_h2_one_chunk(self) -> None:
        content = "# Doc\n\n## Only Section\nSome body text."
        chunks = chunk_markdown(content)
        assert len(chunks) == 1
        assert chunks[0]["heading_path"] == "Doc > Only Section"
        assert "Some body text" in chunks[0]["content"]
        assert chunks[0]["chunk_index"] == 0

    def test_multiple_h2_multiple_chunks(self) -> None:
        content = (
            "# Doc\n\n"
            "## Section A\nBody A.\n\n"
            "## Section B\nBody B.\n\n"
            "## Section C\nBody C.\n"
        )
        chunks = chunk_markdown(content)
        assert len(chunks) == 3
        assert chunks[0]["heading_path"] == "Doc > Section A"
        assert chunks[1]["heading_path"] == "Doc > Section B"
        assert chunks[2]["heading_path"] == "Doc > Section C"
        # Indexes are sequential
        assert [c["chunk_index"] for c in chunks] == [0, 1, 2]

    def test_h2_oversize_splits_by_h3(self) -> None:
        big_body = "x" * 1500
        content = (
            "# Doc\n\n"
            "## Big Section\n"
            "intro paragraph\n\n"
            "### Sub A\n" + big_body + "\n\n"
            "### Sub B\n" + big_body + "\n"
        )
        chunks = chunk_markdown(content, max_chars=1000)
        # The big H2 should split into H3 chunks (Sub A, Sub B), not stay as one
        h3_paths = [c["heading_path"] for c in chunks if "Sub" in c["heading_path"]]
        assert "Doc > Big Section > Sub A" in h3_paths
        assert "Doc > Big Section > Sub B" in h3_paths

    def test_h3_oversize_falls_back_to_windowing(self) -> None:
        # An H3 body bigger than max_chars and with no further structure
        huge = ("paragraph " * 1000).strip()
        content = "# Doc\n\n## Section\n\n### Subsection\n" + huge
        chunks = chunk_markdown(content, max_chars=500, overlap_chars=50)
        # Should produce more than one chunk
        assert len(chunks) > 1
        # All chunks belong to the same heading path
        assert all(c["heading_path"] == "Doc > Section > Subsection" for c in chunks)

    def test_strips_front_matter(self) -> None:
        content = (
            "<!-- domain:ALL | layer:spec | ssot:true | updated:2026-04-06 -->\n"
            "# Doc\n\n"
            "## Section\nbody\n"
        )
        chunks = chunk_markdown(content)
        for c in chunks:
            assert "domain:ALL" not in c["content"]

    def test_content_hash_deterministic(self) -> None:
        content = "# Doc\n\n## Section\nstable body"
        a = chunk_markdown(content)
        b = chunk_markdown(content)
        assert a[0]["content_hash"] == b[0]["content_hash"]
        assert len(a[0]["content_hash"]) == 16

    def test_content_hash_differs_for_different_content(self) -> None:
        a = chunk_markdown("# Doc\n\n## A\nfoo")
        b = chunk_markdown("# Doc\n\n## A\nbar")
        assert a[0]["content_hash"] != b[0]["content_hash"]

    def test_doc_with_no_h2_one_chunk(self) -> None:
        content = "# Doc\n\nJust some flat content with no sections."
        chunks = chunk_markdown(content)
        assert len(chunks) == 1
        assert chunks[0]["heading_path"] == "Doc"


# ---------------------------------------------------------------------------
# load_rag_config
# ---------------------------------------------------------------------------

class TestLoadRagConfig:
    def test_loads_valid_config(self, tmp_config: Path) -> None:
        config = load_rag_config(tmp_config)
        assert "sources" in config
        assert "exclude" in config
        assert len(config["sources"]) >= 4
        assert any(s["type"] == "prd" for s in config["sources"])

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_rag_config(tmp_path / "nope.yaml")

    def test_invalid_sources_type_raises(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.yaml"
        bad.write_text("sources: not_a_list\nexclude: []\n")
        with pytest.raises(ValueError):
            load_rag_config(bad)


# ---------------------------------------------------------------------------
# walk_sources
# ---------------------------------------------------------------------------

class TestWalkSources:
    def test_walks_all_md_files(self, tmp_project: Path, tmp_config: Path) -> None:
        config = load_rag_config(tmp_config)
        files = walk_sources(config["sources"], tmp_project, config["exclude"])
        paths = {str(p[0].relative_to(tmp_project)) for p in files}
        # PRD/01-vision is included
        assert any("PRD/01-vision.md" in p for p in paths)
        # Engineering rule is included
        assert any("engineering/backend-rules.md" in p for p in paths)

    def test_excludes_playbook(self, tmp_project: Path, tmp_config: Path) -> None:
        config = load_rag_config(tmp_config)
        files = walk_sources(config["sources"], tmp_project, config["exclude"])
        paths = {str(p[0].relative_to(tmp_project)) for p in files}
        assert not any("playbooks" in p for p in paths)

    def test_local_exclude_blocks_subdir(
        self, tmp_project: Path, tmp_config: Path
    ) -> None:
        """architecture/ source has local exclude=adr/, so adr files
        come from the dedicated adr/ source — not the architecture one.
        Each ADR file should appear exactly once in the walk."""
        config = load_rag_config(tmp_config)
        files = walk_sources(config["sources"], tmp_project, config["exclude"])
        adr_files = [
            p for p, _ in files if "ADR-001-django.md" in str(p)
        ]
        assert len(adr_files) == 1

    def test_attaches_source_config(self, tmp_project: Path, tmp_config: Path) -> None:
        config = load_rag_config(tmp_config)
        files = walk_sources(config["sources"], tmp_project, config["exclude"])
        for path, source_config in files:
            if "engineering" in str(path):
                assert source_config.get("priority") == 0.7
                assert source_config.get("type") == "engineering"


# ---------------------------------------------------------------------------
# index_docs (end-to-end)
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
            for row in tmp_db.execute(
                "SELECT DISTINCT source_type FROM document_chunks"
            ).fetchall()
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
        chunk_count = tmp_db.execute(
            "SELECT COUNT(*) FROM document_chunks"
        ).fetchone()[0]
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


# ---------------------------------------------------------------------------
# Regression: resolved vs unresolved path handling on macOS (/tmp symlink)
# ---------------------------------------------------------------------------

class TestPathResolutionRegression:
    """Regression guard for the bug caught during Phase B+C end-to-end
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
        row = tmp_db.execute(
            "SELECT source_path FROM document_chunks LIMIT 1"
        ).fetchone()
        assert row is not None
        assert not row[0].startswith("/"), f"expected relative path, got {row[0]!r}"
