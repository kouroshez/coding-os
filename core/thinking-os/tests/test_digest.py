"""
Tests for digest.py — agent identity snapshot (Phase G.10).

Contract:
  - render() is pure: same DB + now → same markdown.
  - Hard budget cap: output ≤ _RENDER_BUDGET_CHARS + tail marker.
  - Sections emitted only when data exists (no empty headings).
  - regenerate() writes to `<root>/.coding-os/digest.md` atomically.
  - Empty DB still produces a valid tiny digest (non-empty, no crash).
  - Pattern selection respects confidence windows:
      * Active Beliefs require confidence ≥ _ACTIVE_MIN.
      * Fading uses [_FADING_MIN, _FADING_MAX] and times_validated ≥ 1.
      * Breakthroughs only last 7 days.
"""

from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db import init_db  # noqa: E402
from digest import (  # noqa: E402
    _ACTIVE_MIN,
    _FADING_MAX,
    _FADING_MIN,
    _RENDER_BUDGET_CHARS,
    read_digest_path,
    regenerate,
    render,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    c = init_db(tmp_path / "test.db")
    yield c
    c.close()


@pytest.fixture
def fixed_now() -> datetime:
    """Stable clock so snapshot tests are deterministic."""
    return datetime(2026, 4, 18, 10, 0, 0, tzinfo=timezone.utc)


def _seed_outcomes(conn: sqlite3.Connection, n_success: int, n_rework: int) -> None:
    for i in range(n_success):
        conn.execute(
            "INSERT INTO task_outcomes (task_id, type, domain, complexity, outcome) "
            "VALUES (?, ?, ?, ?, ?)",
            (f"TASK-S{i:03d}", "feat", "BACKEND", "CLEAR", "success"),
        )
    for i in range(n_rework):
        conn.execute(
            "INSERT INTO task_outcomes (task_id, type, domain, complexity, outcome) "
            "VALUES (?, ?, ?, ?, ?)",
            (f"TASK-R{i:03d}", "fix", "FRONTEND", "COMPLICATED", "rework"),
        )
    conn.commit()


# ---------------------------------------------------------------------------
# render() — pure function contract
# ---------------------------------------------------------------------------

class TestRenderShape:
    def test_empty_db_still_returns_valid_digest(
        self, conn: sqlite3.Connection, fixed_now: datetime
    ) -> None:
        body = render(conn, now=fixed_now)
        assert body.startswith("# Agent Digest — 2026-04-18")
        # Sections that have no data must NOT appear as empty headings
        assert "## Active Beliefs" not in body
        assert "## Fading" not in body
        assert "## Recent Breakthroughs" not in body
        assert "No completed tasks yet." in body

    def test_respects_budget(self, conn: sqlite3.Connection) -> None:
        """Seed an over-size pattern set and verify the budget ceiling holds."""
        long_text = "x" * 200
        for i in range(30):
            conn.execute(
                "INSERT INTO learned_patterns "
                "(pattern, confidence, impact_score, times_validated) "
                "VALUES (?, ?, ?, ?)",
                (f"{long_text} #{i}", 0.9, 0.9, 3),
            )
        conn.commit()
        body = render(conn)
        assert len(body) <= _RENDER_BUDGET_CHARS + len("\n\n…[truncated]\n")

    def test_identity_line_present_when_tasks_exist(
        self, conn: sqlite3.Connection, fixed_now: datetime
    ) -> None:
        _seed_outcomes(conn, n_success=7, n_rework=3)
        body = render(conn, now=fixed_now)
        assert "## Identity" in body
        assert "10 tasks" in body
        assert "70%" in body  # success rate 7/10


# ---------------------------------------------------------------------------
# Belief / fading / breakthrough selection
# ---------------------------------------------------------------------------

class TestSectionSelection:
    def test_active_beliefs_filter_confidence(
        self, conn: sqlite3.Connection, fixed_now: datetime
    ) -> None:
        conn.executemany(
            "INSERT INTO learned_patterns "
            "(pattern, confidence, impact_score, times_validated) VALUES (?, ?, ?, ?)",
            [
                ("keep-me-high", 0.7, 0.8, 2),
                ("keep-me-also", _ACTIVE_MIN, 0.9, 1),
                ("drop-me-low", _ACTIVE_MIN - 0.01, 0.9, 1),
            ],
        )
        conn.commit()
        body = render(conn, now=fixed_now)
        assert "keep-me-high" in body
        assert "keep-me-also" in body
        assert "drop-me-low" not in body

    def test_fading_window(
        self, conn: sqlite3.Connection, fixed_now: datetime
    ) -> None:
        conn.executemany(
            "INSERT INTO learned_patterns "
            "(pattern, confidence, times_validated) VALUES (?, ?, ?)",
            [
                ("fading-in-window", _FADING_MIN + 0.05, 2),
                ("fading-never-validated", _FADING_MIN + 0.05, 0),
                ("above-fading", _FADING_MAX + 0.01, 2),
                ("below-fading", _FADING_MIN - 0.01, 2),
            ],
        )
        conn.commit()
        body = render(conn, now=fixed_now)
        assert "fading-in-window" in body
        # Not in fading section (outside window or never validated)
        assert "fading-never-validated" not in body

    def test_breakthroughs_last_7_days_only(
        self, conn: sqlite3.Connection, fixed_now: datetime
    ) -> None:
        # recent
        conn.execute(
            "INSERT INTO outcome_history "
            "(task_id, outcome, is_breakthrough, narrative_key_insight) "
            "VALUES (?, 'success', 1, ?)",
            ("TASK-RECENT", "Use Decimal for money handling"),
        )
        # old: 10 days back
        conn.execute(
            "INSERT INTO outcome_history "
            "(task_id, outcome, is_breakthrough, narrative_key_insight, created_at) "
            "VALUES (?, 'success', 1, ?, datetime('now', '-10 days'))",
            ("TASK-OLD", "old insight"),
        )
        conn.commit()
        body = render(conn, now=fixed_now)
        assert "TASK-RECENT" in body
        assert "TASK-OLD" not in body

    def test_preferences_memory_types(
        self, conn: sqlite3.Connection, fixed_now: datetime
    ) -> None:
        conn.executemany(
            "INSERT INTO learned_patterns "
            "(pattern, memory_type, confidence) VALUES (?, ?, ?)",
            [
                ("prefer-terse-responses", "decision", 0.7),
                ("workflow-commit-often", "workflow", 0.6),
                ("random-pattern", "pattern", 0.9),  # NOT in preferences section
            ],
        )
        conn.commit()
        body = render(conn, now=fixed_now)
        assert "prefer-terse-responses" in body
        assert "workflow-commit-often" in body
        # Preferences section only includes workflow/decision memory_types


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

class TestDeterminism:
    def test_same_state_same_output(
        self, conn: sqlite3.Connection, fixed_now: datetime
    ) -> None:
        conn.execute(
            "INSERT INTO learned_patterns (pattern, confidence, impact_score, times_validated) "
            "VALUES (?, ?, ?, ?)",
            ("Money → Decimal", 0.85, 0.9, 5),
        )
        conn.commit()
        a = render(conn, now=fixed_now)
        b = render(conn, now=fixed_now)
        assert a == b


# ---------------------------------------------------------------------------
# regenerate() — filesystem side
# ---------------------------------------------------------------------------

class TestRegenerate:
    def test_writes_to_expected_path(
        self, conn: sqlite3.Connection, tmp_path: Path, fixed_now: datetime
    ) -> None:
        result = regenerate(conn, project_root=tmp_path, now=fixed_now)
        target = tmp_path / ".coding-os" / "digest.md"
        assert target.exists()
        assert result["status"] == "ok"
        assert result["path"] == str(target)
        assert result["size_chars"] > 0
        assert target.read_text().startswith("# Agent Digest —")

    def test_overwrites_existing(
        self, conn: sqlite3.Connection, tmp_path: Path, fixed_now: datetime
    ) -> None:
        (tmp_path / ".coding-os").mkdir(parents=True, exist_ok=True)
        (tmp_path / ".coding-os" / "digest.md").write_text("STALE")
        regenerate(conn, project_root=tmp_path, now=fixed_now)
        content = (tmp_path / ".coding-os" / "digest.md").read_text()
        assert "STALE" not in content
        assert content.startswith("# Agent Digest —")

    def test_read_digest_path_uses_resolve(self, tmp_path: Path) -> None:
        p = read_digest_path(tmp_path)
        assert p.name == "digest.md"
        assert p.parent.name == ".coding-os"
