"""The every-10 task-done learn_extract path must respect the shared .last-extract
marker (audit: it bypassed the marker, double-extracting with nightly/responsive)."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
for _p in (_ROOT, _ROOT / "src", _ROOT / "src" / "core", _ROOT / "src" / "core" / "thinking_os"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from cli import board_commands  # noqa: E402
from database import init_db  # noqa: E402
from scheduled._activity import outcomes_since_marker  # noqa: E402
from scheduled._state import state_dir  # noqa: E402


@pytest.fixture
def project(tmp_path, monkeypatch):
    db = tmp_path / ".coding-os" / "coding-os.db"
    db.parent.mkdir(parents=True)
    monkeypatch.setenv("COS_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("COS_DB_PATH", str(db))
    conn = init_db(db)
    # 10 outcomes (count % 10 == 0 triggers the every-10 path), aged so the
    # post-extract marker is unambiguously newer than every outcome.
    for i in range(10):
        conn.execute(
            "INSERT INTO task_outcomes (task_id, type, domain, complexity, outcome, skills_used, created_at) "
            "VALUES (?, 'feat', 'INFRA', 'CLEAR', 'success', 'clean-code', datetime('now', '-1 hour'))",
            (f"TASK-{i}",),
        )
    conn.commit()
    yield tmp_path, db, conn
    conn.close()


def test_every10_touches_shared_marker(project) -> None:
    tmp_path, db, conn = project
    marker = state_dir(tmp_path) / ".last-extract"
    assert not marker.exists()

    board_commands._record_brain_outcome_safe(conn, "TASK-9")

    assert marker.exists()  # the every-10 path now stamps the shared marker
    # idempotency: no outcomes are newer than the marker, so nightly/responsive
    # (which gate on outcomes_since_marker) will skip — no double extraction.
    assert outcomes_since_marker(db, marker) == 0


def test_skips_when_marker_already_fresh(project) -> None:
    tmp_path, db, conn = project
    from scheduled._state import touch_marker

    marker = state_dir(tmp_path) / ".last-extract"
    marker.parent.mkdir(parents=True, exist_ok=True)
    touch_marker(marker)  # simulate another path having just extracted
    # learned_patterns starts empty; with the marker fresh + no new outcomes,
    # the every-10 path must NOT mint anything.
    board_commands._record_brain_outcome_safe(conn, "TASK-9")
    n = conn.execute(
        "SELECT COUNT(*) FROM learned_patterns WHERE source = 'commit' OR source = 'friction'"
    ).fetchone()[0]
    assert n == 0  # skipped — no extraction because outcomes_since_marker == 0
