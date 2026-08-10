"""Narrative authoring: slug, markdown shape, and the filed insight doc."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from database import init_db
from tools._learning_narrative import (
    _file_back_narrative_safe,
    _format_narrative_markdown,
    _slugify,
    learn_narrative,
)
from tools._learning_store import _derive_project_root


@pytest.fixture
def conn(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    c = init_db(tmp_path / "test.db")
    yield c
    c.close()


@pytest.fixture
def project_conn(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    """DB in <tmp>/.coding-os/coding-os.db with a sibling docs/ dir."""
    state_dir = tmp_path / ".coding-os"
    state_dir.mkdir()
    (tmp_path / "docs").mkdir()
    c = init_db(state_dir / "coding-os.db")
    yield c
    c.close()


class TestSlugify:
    def test_lowercases_and_dashes(self) -> None:
        assert _slugify("Mock AT THE Boundary") == "mock-at-the-boundary"

    def test_collapses_non_alnum_runs(self) -> None:
        assert _slugify("hello!!  world??") == "hello-world"

    def test_empty_input_returns_untitled(self) -> None:
        assert _slugify("   ") == "untitled"

    def test_truncates_to_max_len(self) -> None:
        result = _slugify("a" * 80, max_len=20)
        assert len(result) == 20


class TestDeriveProjectRoot:
    def test_project_root_from_coding_os_layout(
        self, project_conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        root = _derive_project_root(project_conn)
        assert root is not None
        assert root.resolve() == tmp_path.resolve()

    def test_returns_none_for_non_coding_os_layout(self, conn: sqlite3.Connection) -> None:
        # Default fixture DB sits at tmp_path/test.db (no .coding-os/)
        assert _derive_project_root(conn) is None


class TestFormatNarrativeMarkdown:
    def test_includes_task_id_and_insight_in_heading(self) -> None:
        md = _format_narrative_markdown(
            task_id="TASK-900",
            domain="BACKEND",
            key_insight="Mock at the boundary, not at the leaf",
            what_failed="Mocked the whole JWT lib",
            what_worked="Real tokens in test fixtures",
            history_id=42,
            pattern_id=99,
        )
        assert "# TASK-900: Mock at the boundary, not at the leaf" in md
        assert "**Domain:** BACKEND" in md
        assert "outcome_history#42" in md
        assert "learned_patterns#99" in md
        assert "Real tokens in test fixtures" in md

    def test_missing_failed_or_worked_renders_placeholder(self) -> None:
        md = _format_narrative_markdown(
            task_id="TASK-901",
            domain=None,
            key_insight="x",
            what_failed="",
            what_worked="",
            history_id=1,
            pattern_id=1,
        )
        assert "_(not recorded)_" in md
        assert "**Domain:** n/a" in md


class TestFileBackNarrative:
    def test_writes_markdown_under_docs_insights(
        self, project_conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        result = _file_back_narrative_safe(
            conn=project_conn,
            task_id="TASK-700",
            domain="BACKEND",
            key_insight="Mock at the boundary",
            what_failed="Mocked internals",
            what_worked="Mocked at the HTTP edge",
            history_id=7,
            pattern_id=11,
        )
        assert result is not None
        assert result.exists()
        target_dir = tmp_path / "docs" / "insights"
        assert result.parent.resolve() == target_dir.resolve()
        content = result.read_text(encoding="utf-8")
        assert "TASK-700" in content
        assert "Mock at the boundary" in content

    def test_skips_when_no_docs_dir(self, tmp_path: Path) -> None:
        state_dir = tmp_path / ".coding-os"
        state_dir.mkdir()
        # Deliberately NOT creating tmp_path/docs/
        c = init_db(state_dir / "coding-os.db")
        try:
            result = _file_back_narrative_safe(
                conn=c,
                task_id="TASK-701",
                domain=None,
                key_insight="x",
                what_failed="",
                what_worked="",
                history_id=1,
                pattern_id=1,
            )
            assert result is None
        finally:
            c.close()

    def test_skips_for_non_coding_os_layout(self, conn: sqlite3.Connection) -> None:
        result = _file_back_narrative_safe(
            conn=conn,
            task_id="TASK-702",
            domain=None,
            key_insight="x",
            what_failed="",
            what_worked="",
            history_id=1,
            pattern_id=1,
        )
        assert result is None

    def test_learn_narrative_reports_filed_path(
        self, project_conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        project_conn.execute(
            "INSERT INTO task_outcomes (task_id, type, domain, complexity, outcome) "
            "VALUES (?, ?, ?, ?, ?)",
            ("TASK-703", "fix", "BACKEND", "COMPLICATED", "success"),
        )
        project_conn.commit()

        result = learn_narrative(
            project_conn,
            task_id="TASK-703",
            what_failed="A",
            what_worked="B",
            key_insight="Lesson learned about retries",
        )
        assert result.get("filed_path")
        filed = Path(result["filed_path"])
        assert filed.exists()
        assert filed.parent.resolve() == (tmp_path / "docs" / "insights").resolve()

    def test_learn_narrative_no_filed_path_without_project_layout(
        self, conn: sqlite3.Connection
    ) -> None:
        result = learn_narrative(
            conn,
            task_id="TASK-704",
            key_insight="Some insight",
        )
        assert result.get("filed_path") is None

    def test_narrative_overwrites_same_slug(self, project_conn: sqlite3.Connection) -> None:
        first = _file_back_narrative_safe(
            conn=project_conn,
            task_id="TASK-705",
            domain="BACKEND",
            key_insight="Same insight",
            what_failed="v1",
            what_worked="v1",
            history_id=1,
            pattern_id=1,
        )
        second = _file_back_narrative_safe(
            conn=project_conn,
            task_id="TASK-705",
            domain="BACKEND",
            key_insight="Same insight",
            what_failed="v2-updated",
            what_worked="v2-updated",
            history_id=1,
            pattern_id=1,
        )
        assert first == second
        assert "v2-updated" in second.read_text(encoding="utf-8")
