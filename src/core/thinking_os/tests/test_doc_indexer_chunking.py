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

import sqlite3
import sys
from pathlib import Path

import pytest

# Make doc_indexer + db importable from the package root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import embeddings
from database import init_db
from doc_indexer import (
    _build_heading_path,
    _extract_h1,
    _strip_front_matter,
    chunk_markdown,
    load_rag_config,
    walk_sources,
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
            "# Doc\n\n## Section A\nBody A.\n\n## Section B\nBody B.\n\n## Section C\nBody C.\n"
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

    def test_local_exclude_blocks_subdir(self, tmp_project: Path, tmp_config: Path) -> None:
        """architecture/ source has local exclude=adr/, so adr files
        come from the dedicated adr/ source — not the architecture one.
        Each ADR file should appear exactly once in the walk."""
        config = load_rag_config(tmp_config)
        files = walk_sources(config["sources"], tmp_project, config["exclude"])
        adr_files = [p for p, _ in files if "ADR-001-django.md" in str(p)]
        assert len(adr_files) == 1

    def test_attaches_source_config(self, tmp_project: Path, tmp_config: Path) -> None:
        config = load_rag_config(tmp_config)
        files = walk_sources(config["sources"], tmp_project, config["exclude"])
        for path, source_config in files:
            if "engineering" in str(path):
                assert source_config.get("priority") == 0.7
                assert source_config.get("type") == "engineering"
