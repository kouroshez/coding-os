"""Pytest coverage for /api/patterns endpoints (tier field, roi, validate).

The Memory page consumes these — the tier field, the roi trend, and the
thumbs validate endpoint (cos_learn_validate) that closes the learning loop.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_REPO_ROOT = Path(__file__).resolve().parent.parent
for _p in (_REPO_ROOT, _REPO_ROOT / "src" / "core", _REPO_ROOT / "src" / "core" / "thinking_os"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from core.web.server import create_app  # noqa: E402
from thinking_os.database import init_db  # noqa: E402


def _seed(conn: sqlite3.Connection) -> None:
    conn.execute(
        "INSERT INTO learned_patterns (pattern, memory_type, source, confidence, times_validated, concepts) "
        "VALUES (?, 'lesson', 'friction', 0.8, 3, '[]')",
        ("Recurring completion gap (2 occurrences): left a task open → close it before ending",),
    )
    conn.execute(
        "INSERT INTO learned_patterns (pattern, memory_type, source, confidence, times_validated, concepts) "
        "VALUES (?, 'stat', 'learn_extract', 0.9, 5, '[]')",
        ("INFRA domain succeeds at 100% (10/10 tasks) — reliable baseline",),
    )
    # observations for the roi endpoint (HAVING total >= 5 keeps the session)
    for i in range(6):
        conn.execute(
            "INSERT INTO observations (session_id, tool_name, observation_type, memory_type, "
            "impact_score, title, narrative, content_hash) VALUES (?, 'Edit', 'edit', ?, 0.5, ?, ?, ?)",
            ("ses-roi-1", "error" if i < 2 else "discovery", f"t{i}", f"n{i}", f"hh-{i}"),
        )
    conn.commit()


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / ".coding-os" / "coding-os.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    # COS_DB_PATH has top resolution priority → route + test share one DB.
    monkeypatch.setenv("COS_DB_PATH", str(db_path))
    conn = init_db(db_path)
    _seed(conn)
    conn.close()
    app = create_app()
    with TestClient(app) as c:
        yield c


def _lesson_id(c: TestClient) -> int:
    pats = c.get("/api/patterns").json()["data"]["patterns"]
    return next(p["id"] for p in pats if p["memory_type"] == "lesson")


def test_patterns_list_carries_tier(client):
    resp = client.get("/api/patterns")
    assert resp.status_code == 200
    pats = resp.json()["data"]["patterns"]
    assert pats
    assert all("tier" in p for p in pats)
    lesson = next(p for p in pats if p["memory_type"] == "lesson")
    assert lesson["tier"] == "Trusted"  # confidence 0.8 + times_validated 3


def test_patterns_roi_shape(client):
    resp = client.get("/api/patterns/roi")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "sessions" in data
    assert "trend" in data


def test_validate_pattern_boosts_confidence(client):
    pid = _lesson_id(client)
    resp = client.post(f"/api/patterns/{pid}/validate", json={"was_helpful": True})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["new_confidence"] >= data["old_confidence"]
    assert data["status"] in ("validated", "throttled")


def test_validate_pattern_penalizes_on_thumbs_down(client):
    pid = _lesson_id(client)
    resp = client.post(f"/api/patterns/{pid}/validate", json={"was_helpful": False})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["new_confidence"] < data["old_confidence"]


def test_validate_pattern_not_found(client):
    resp = client.post("/api/patterns/999999/validate", json={"was_helpful": False})
    assert resp.status_code == 404
    assert "error" in resp.json()
