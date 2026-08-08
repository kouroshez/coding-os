"""The every-10 task-done learn_extract path must respect the shared .last-extract
marker (audit: it bypassed the marker, double-extracting with nightly/responsive)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
for _p in (_ROOT, _ROOT / "src", _ROOT / "src" / "core", _ROOT / "src" / "core" / "thinking_os"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from database import init_db

from cli import board_commands
from scheduled._activity import outcomes_since_marker
from scheduled._state import state_dir


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


def test_skips_when_marker_already_fresh(project, monkeypatch) -> None:
    # Discriminating: spy on learn_extract so we prove the MARKER gates the call,
    # not that the empty corpus happens to mint nothing (the old tautology).
    tmp_path, _db, conn = project
    import thinking_os.tools.learning as learning_mod
    from scheduled._state import touch_marker

    calls: list[int] = []
    monkeypatch.setattr(
        learning_mod, "learn_extract", lambda c, **k: calls.append(1) or {"extracted": []}
    )
    marker = state_dir(tmp_path) / ".last-extract"
    marker.parent.mkdir(parents=True, exist_ok=True)
    touch_marker(marker)  # fresh marker — all 10 outcomes predate it

    board_commands._record_brain_outcome_safe(conn, "TASK-9")
    assert calls == []  # extraction SKIPPED because outcomes_since_marker == 0


def test_extracts_when_marker_stale(project, monkeypatch) -> None:
    # Control for the above: with NO fresh marker, the same 10 outcomes ARE
    # "since" → learn_extract is actually invoked. Proves the gate has two sides.
    _tmp_path, _db, conn = project
    import thinking_os.tools.learning as learning_mod

    calls: list[int] = []
    monkeypatch.setattr(
        learning_mod, "learn_extract", lambda c, **k: calls.append(1) or {"extracted": []}
    )

    board_commands._record_brain_outcome_safe(conn, "TASK-9")  # marker absent
    assert calls == [1]  # extraction RAN because outcomes exist since the (absent) marker
