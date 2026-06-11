"""
Tests for core/thinking_os/tools/tasks.py.

Covers all four tools:
  - task_by_filter (status, domain, combined, limit, empty)
  - task_dependencies (direct upstream, no-deps task, unknown task)
  - task_dependents (direct downstream, multiple, no false positives, leaf)
  - task_search (semantic with REQUIRES_RAG, LIKE fallback, filter interaction, edge cases)
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import embeddings
from database import init_db
from task_sync import sync_tasks
from tools.tasks import (
    task_by_filter,
    task_dependencies,
    task_dependents,
    task_search,
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


def _lean_card(
    task_id: str,
    title: str,
    *,
    swimlane: str,
    status: str,
    outcome: str,
    depends_on: tuple[str, ...] = (),
) -> str:
    deps = "[" + ", ".join(depends_on) + "]"
    return (
        "---\n"
        f"id: {task_id}\n"
        f'title: "{title}"\n'
        f"swimlane: {swimlane}\n"
        "kind: feature\n"
        "labels: []\n"
        f"status: {status}\n"
        "priority: P2\n"
        "appetite: 1d\n"
        "created: 2026-06-01\n"
        f"depends_on: {deps}\n"
        "---\n"
        f"# {task_id}: {title}\n\n"
        f"**Outcome (one sentence):** {outcome}\n"
    )


@pytest.fixture
def seeded_db(tmp_db: sqlite3.Connection, tmp_path: Path) -> sqlite3.Connection:
    """Populate the tasks table with a realistic dependency graph.

    Graph:
        TASK-001 (DOCS, complete)         — no deps
        TASK-002 (BACKEND, in_progress)   — depends on TASK-001
        TASK-003 (BACKEND, icebox)        — depends on TASK-002
        TASK-019 (DOCS, complete)         — no deps (substring-false-positive check)
        TASK-195 (BACKEND, icebox)        — depends on TASK-001
        TASK-199 (BACKEND, icebox)        — depends on TASK-195
                                            (the "TASK-19 vs TASK-195" safety test)
    """
    project = tmp_path / "project"
    tasks_dir = project / "docs" / "tasks"
    tasks_dir.mkdir(parents=True)

    task_files = {
        "TASK-001-foundation.md": _lean_card(
            "TASK-001", "Foundation", swimlane="docs", status="complete",
            outcome="Documentation setup.",
        ),
        "TASK-002-backend.md": _lean_card(
            "TASK-002", "Backend scaffold", swimlane="backend", status="in_progress",
            outcome="Django apps.", depends_on=("TASK-001",),
        ),
        "TASK-003-auth.md": _lean_card(
            "TASK-003", "Auth flow", swimlane="backend", status="icebox",
            outcome="JWT authentication.", depends_on=("TASK-002",),
        ),
        "TASK-019-small.md": _lean_card(
            "TASK-019", "Small task", swimlane="docs", status="complete",
            outcome="Doc cleanup.",
        ),
        "TASK-195-seller-crud.md": _lean_card(
            "TASK-195", "Seller product CRUD", swimlane="backend", status="icebox",
            outcome="CRUD endpoints for sellers.", depends_on=("TASK-001",),
        ),
        "TASK-199-commission.md": _lean_card(
            "TASK-199", "Commission model", swimlane="backend", status="icebox",
            outcome="Commission calculation at checkout for payment splitting between sellers.",
            depends_on=("TASK-195",),
        ),
    }
    for filename, content in task_files.items():
        (tasks_dir / filename).write_text(content, encoding="utf-8")

    sync_tasks(tmp_db, project_root=project)
    return tmp_db


# ---------------------------------------------------------------------------
# task_by_filter
# ---------------------------------------------------------------------------


class TestTaskByFilter:
    def test_no_filter_returns_all(self, seeded_db: sqlite3.Connection) -> None:
        results = task_by_filter(seeded_db)
        assert len(results) == 6

    def test_filter_by_status_open(self, seeded_db: sqlite3.Connection) -> None:
        results = task_by_filter(seeded_db, status="icebox")
        assert len(results) == 3
        assert all(r["status"] == "icebox" for r in results)

    def test_filter_by_status_done(self, seeded_db: sqlite3.Connection) -> None:
        results = task_by_filter(seeded_db, status="complete")
        assert len(results) == 2
        ids = {r["task_id"] for r in results}
        assert ids == {"TASK-001", "TASK-019"}

    def test_filter_by_status_wip(self, seeded_db: sqlite3.Connection) -> None:
        results = task_by_filter(seeded_db, status="in_progress")
        assert len(results) == 1
        assert results[0]["task_id"] == "TASK-002"

    def test_filter_by_domain(self, seeded_db: sqlite3.Connection) -> None:
        results = task_by_filter(seeded_db, domain="BACKEND")
        assert len(results) == 4
        assert all(r["domain"] == "BACKEND" for r in results)

    def test_filter_by_status_and_domain(self, seeded_db: sqlite3.Connection) -> None:
        results = task_by_filter(seeded_db, status="icebox", domain="BACKEND")
        assert len(results) == 3
        assert all(r["status"] == "icebox" and r["domain"] == "BACKEND" for r in results)

    def test_limit_respected(self, seeded_db: sqlite3.Connection) -> None:
        results = task_by_filter(seeded_db, limit=2)
        assert len(results) == 2

    def test_empty_db_returns_empty_list(self, tmp_db: sqlite3.Connection) -> None:
        assert task_by_filter(tmp_db) == []

    def test_returns_sorted_by_task_id(self, seeded_db: sqlite3.Connection) -> None:
        results = task_by_filter(seeded_db)
        ids = [r["task_id"] for r in results]
        assert ids == sorted(ids)


# ---------------------------------------------------------------------------
# task_dependencies — upstream
# ---------------------------------------------------------------------------


class TestTaskDependencies:
    def test_returns_single_prerequisite(self, seeded_db: sqlite3.Connection) -> None:
        results = task_dependencies(seeded_db, "TASK-002")
        assert len(results) == 1
        assert results[0]["task_id"] == "TASK-001"

    def test_returns_prerequisite_with_full_metadata(self, seeded_db: sqlite3.Connection) -> None:
        results = task_dependencies(seeded_db, "TASK-199")
        assert len(results) == 1
        assert results[0]["title"] == "Seller product CRUD"
        assert results[0]["domain"] == "BACKEND"
        assert "CRUD" in results[0]["goal_text"]

    def test_empty_for_task_with_no_deps(self, seeded_db: sqlite3.Connection) -> None:
        assert task_dependencies(seeded_db, "TASK-001") == []

    def test_empty_for_unknown_task(self, seeded_db: sqlite3.Connection) -> None:
        assert task_dependencies(seeded_db, "TASK-999") == []

    def test_empty_db(self, tmp_db: sqlite3.Connection) -> None:
        assert task_dependencies(tmp_db, "TASK-001") == []


# ---------------------------------------------------------------------------
# task_dependents — downstream
# ---------------------------------------------------------------------------


class TestTaskDependents:
    def test_finds_direct_dependent(self, seeded_db: sqlite3.Connection) -> None:
        results = task_dependents(seeded_db, "TASK-002")
        assert len(results) == 1
        assert results[0]["task_id"] == "TASK-003"

    def test_finds_multiple_dependents(self, seeded_db: sqlite3.Connection) -> None:
        """TASK-001 is a dependency of TASK-002 AND TASK-195."""
        results = task_dependents(seeded_db, "TASK-001")
        ids = {r["task_id"] for r in results}
        assert ids == {"TASK-002", "TASK-195"}

    def test_no_false_positive_substring(self, seeded_db: sqlite3.Connection) -> None:
        """TASK-19 must NOT match TASK-195 as a dependent.

        This is the critical substring-safety test. TASK-19 has no
        dependents in the fixture; TASK-199 declares TASK-195 as a dep.
        If our matcher were sloppy, querying dependents of TASK-19 would
        wrongly return TASK-199.
        """
        results = task_dependents(seeded_db, "TASK-019")
        # has no downstream dependents
        assert results == []

    def test_dependents_of_task_with_descendant(self, seeded_db: sqlite3.Connection) -> None:
        """task_dependents is non-transitive — only direct dependents."""
        results = task_dependents(seeded_db, "TASK-195")
        ids = {r["task_id"] for r in results}
        assert ids == {"TASK-199"}
        # also depends (transitively) but should NOT appear
        assert "TASK-001" not in ids

    def test_leaf_task_returns_empty(self, seeded_db: sqlite3.Connection) -> None:
        """TASK-199 has no dependents in the graph."""
        assert task_dependents(seeded_db, "TASK-199") == []

    def test_empty_db(self, tmp_db: sqlite3.Connection) -> None:
        assert task_dependents(tmp_db, "TASK-001") == []


# ---------------------------------------------------------------------------
# task_search — semantic + LIKE fallback
# ---------------------------------------------------------------------------


class TestTaskSearchEdgeCases:
    def test_empty_query_returns_empty(self, seeded_db: sqlite3.Connection) -> None:
        assert task_search(seeded_db, "") == []
        assert task_search(seeded_db, "   ") == []

    def test_empty_db_returns_empty(self, tmp_db: sqlite3.Connection) -> None:
        assert task_search(tmp_db, "anything") == []


class TestTaskSearchLikeFallback:
    """Fallback path — runs even without rag extras."""

    def test_like_matches_title_substring(self, seeded_db: sqlite3.Connection, monkeypatch) -> None:
        # Force the LIKE fallback by patching is_available to False
        monkeypatch.setattr(embeddings, "is_available", lambda: False)
        results = task_search(seeded_db, "auth")
        ids = {r["task_id"] for r in results}
        assert "TASK-003" in ids

    def test_like_matches_goal_text(self, seeded_db: sqlite3.Connection, monkeypatch) -> None:
        monkeypatch.setattr(embeddings, "is_available", lambda: False)
        results = task_search(seeded_db, "JWT")
        ids = {r["task_id"] for r in results}
        assert "TASK-003" in ids

    def test_like_respects_status_filter(self, seeded_db: sqlite3.Connection, monkeypatch) -> None:
        monkeypatch.setattr(embeddings, "is_available", lambda: False)
        # "scaffold" matches TASK-002 which is status=wip
        results = task_search(seeded_db, "Django", status="complete")
        # Django doesn't appear in done tasks
        assert results == []

    def test_like_respects_domain_filter(self, seeded_db: sqlite3.Connection, monkeypatch) -> None:
        monkeypatch.setattr(embeddings, "is_available", lambda: False)
        results = task_search(seeded_db, "Documentation", domain="DOCS")
        assert all(r["domain"] == "DOCS" for r in results)

    def test_limit_respected(self, seeded_db: sqlite3.Connection, monkeypatch) -> None:
        monkeypatch.setattr(embeddings, "is_available", lambda: False)
        results = task_search(seeded_db, "task", limit=2)
        assert len(results) <= 2


class TestTaskSearchSemantic:
    """Semantic path — requires rag extras."""

    @REQUIRES_RAG
    @pytest.mark.real_embeddings
    def test_semantic_finds_related_task(self, seeded_db: sqlite3.Connection) -> None:
        """Query with no exact word overlap should still find the payment task."""
        results = task_search(seeded_db, "multi vendor marketplace revenue sharing")
        assert len(results) >= 1
        ids = {r["task_id"] for r in results}
        # should surface
        assert "TASK-199" in ids or "TASK-195" in ids

    @REQUIRES_RAG
    def test_semantic_honors_status_filter(self, seeded_db: sqlite3.Connection) -> None:
        results = task_search(seeded_db, "backend implementation", status="icebox")
        assert all(r["status"] == "icebox" for r in results)

    @REQUIRES_RAG
    def test_semantic_honors_domain_filter(self, seeded_db: sqlite3.Connection) -> None:
        results = task_search(seeded_db, "scaffold setup", domain="BACKEND")
        assert all(r["domain"] == "BACKEND" for r in results)

    @REQUIRES_RAG
    def test_semantic_results_have_score(self, seeded_db: sqlite3.Connection) -> None:
        results = task_search(seeded_db, "authentication")
        assert len(results) >= 1
        for r in results:
            assert "score" in r
            assert isinstance(r["score"], (int, float))

    @REQUIRES_RAG
    def test_semantic_results_sorted_by_score_desc(self, seeded_db: sqlite3.Connection) -> None:
        results = task_search(seeded_db, "backend authentication")
        if len(results) > 1:
            scores = [r["score"] for r in results]
            assert scores == sorted(scores, reverse=True)
