"""Coverage for the unified live-agent endpoint GET /api/presence/agents (TASK-191)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_REPO_ROOT = Path(__file__).resolve().parent.parent
for _p in (_REPO_ROOT, _REPO_ROOT / "src" / "core"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from core.web.server import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    state = tmp_path / ".coding-os"
    sessions = state / "claude" / "sessions"
    sessions.mkdir(parents=True)
    sid = "ses-claude-test-uvw"
    (state / "claude" / "session-id").write_text(sid)
    (sessions / f"{sid}.json").write_text(
        json.dumps(
            {
                "agent": "claude",
                "session_id": sid,
                "model": "claude-opus-4-8",
                "sdk_uuid": "SDK-XYZ",
                "last_tool_at": 9_999_999_999,
                "pid": os.getpid(),
            }
        )
    )
    # _agent_runtime strips the "<sid> " prefix from per-panel markers.
    (state / "claude" / ".task-current").write_text(f"{sid} TASK-777")
    (state / "claude" / ".thinking_os-gate").write_text(f"{sid} COMPLEX 6")
    (state / "claude" / ".active-skill").write_text(f"{sid} graph-explorer")
    (state / "claude" / ".role").write_text("architect")
    monkeypatch.setenv("COS_STATE_DIR", str(state))
    monkeypatch.setenv("COS_PROJECT_ROOT", str(tmp_path))
    with TestClient(create_app()) as c:
        yield c


def test_presence_agents_unifies_all_fields(client):
    r = client.get("/api/presence/agents")
    assert r.status_code == 200
    agents = r.json()["data"]["agents"]
    claude = next((a for a in agents if a["agent"] == "claude"), None)
    assert claude is not None
    assert claude["model"] == "claude-opus-4-8"
    assert claude["sdk_uuid"] == "SDK-XYZ"
    assert claude["task"] == "TASK-777"
    assert claude["gate"] == "COMPLEX 6"
    assert claude["skill_active"] == "graph-explorer"
    assert claude["role"] == "architect"
    assert isinstance(claude["chain"], list)
    assert "state" in claude
