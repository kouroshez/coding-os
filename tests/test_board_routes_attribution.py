"""Board move/reposition routes must attribute unowned panel actions to the
human actor — left unattributed, resolve_agent_session stamps whatever agent
session is active, recording a human drag as agent work (hub-architecture.md
§ Actor attribution contract).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_REPO_ROOT = Path(__file__).resolve().parent.parent
for _p in (_REPO_ROOT, _REPO_ROOT / "src" / "core", _REPO_ROOT / "src" / "core" / "thinking_os"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from core.thinking_os import database as db
from core.web.server import create_app


@pytest.fixture
def board_client(tmp_path, monkeypatch):
    proj = tmp_path / "proj"
    (proj / "docs" / "tasks").mkdir(parents=True)
    state = proj / ".coding-os"
    state.mkdir()
    conn = db.init_db(state / "coding-os.db")
    conn.close()
    monkeypatch.setenv("COS_PROJECT_ROOT", str(proj))
    monkeypatch.setenv("COS_STATE_DIR", str(state))
    # Scrub live-session markers so a developer's in-panel run cannot leak an
    # agent session into the attribution under test.
    for var in ("COS_PANEL_DIR", "COS_AGENT_DIR", "COS_SESSION_FILE", "COS_SESSION_ID"):
        monkeypatch.delenv(var, raising=False)
    with TestClient(create_app()) as client:
        yield client


def _create_task(client: TestClient) -> str:
    resp = client.post(
        "/api/board/create",
        json={"title": "Drag target", "swimlane": "core", "kind": "chore"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["task_id"]


def test_unattributed_move_is_recorded_as_human(board_client):
    task_id = _create_task(board_client)
    resp = board_client.post("/api/board/move", json={"task_id": task_id, "to": "archive"})
    assert resp.status_code == 200, resp.text
    events = board_client.get(f"/api/board/task/{task_id}/history").json()["data"]["events"]
    move_event = next(e for e in events if e.get("to") == "archive")
    assert move_event["actor"]["type"] == "human"


def test_unattributed_reposition_is_recorded_as_human(board_client):
    task_id = _create_task(board_client)
    resp = board_client.post("/api/board/reposition", json={"task_id": task_id, "to": "archive"})
    assert resp.status_code == 200, resp.text
    events = board_client.get(f"/api/board/task/{task_id}/history").json()["data"]["events"]
    move_event = next(e for e in events if e.get("to") == "archive")
    assert move_event["actor"]["type"] == "human"
