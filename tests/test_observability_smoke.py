"""Smoke tests for the unified observability API surface."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if str(_REPO_ROOT / "src" / "core") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src" / "core"))

from core.web.server import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    state = tmp_path / ".coding-os"
    monkeypatch.setenv("COS_STATE_DIR", str(state))
    monkeypatch.setenv("COS_HOOK_LOG", str(state / ".hooks.log"))
    app = create_app()
    with TestClient(app) as c:
        yield c, state


def test_observability_smoke_empty_state_returns_200(client):
    c, _ = client
    sessions_resp = c.get("/api/observability/sessions")
    assert sessions_resp.status_code == 200
    sessions_data = sessions_resp.json()["data"]
    assert sessions_data["sessions"] == []
    assert sessions_data["count"] == 0

    timeline_resp = c.get("/api/observability/timeline")
    assert timeline_resp.status_code == 200
    timeline_data = timeline_resp.json()["data"]
    assert timeline_data["events"] == []
    assert timeline_data["count"] == 0


def test_observability_smoke_single_session_roundtrip(client):
    c, state = client
    sid = "ses-claude-20260425-200000-smoke"
    (state / "claude" / "traces").mkdir(parents=True)
    (state / "claude" / "sessions").mkdir(parents=True)
    (state / "claude" / "traces" / f"{sid}.jsonl").write_text(
        json.dumps({"kind": "compose_done", "ts": 1, "agent": "claude"}) + "\n",
        encoding="utf-8",
    )
    (state / "claude" / "sessions" / f"{sid}.json").write_text(
        json.dumps({"session_id": sid, "started_at": 1, "last_tool_at": 2, "agent": "claude"}),
        encoding="utf-8",
    )
    (state / ".hooks.log").write_text(
        "[2026-04-25T20:00:10Z] [session-context] [fire] "
        f"agent=claude session={sid} task=TASK-126 detail=smoke\n",
        encoding="utf-8",
    )

    sessions_resp = c.get("/api/observability/sessions")
    assert sessions_resp.status_code == 200
    rows = sessions_resp.json()["data"]["sessions"]
    row = next(r for r in rows if r["session_id"] == sid)
    assert row["source"] == "trace+session"

    timeline_resp = c.get(
        "/api/observability/timeline",
        params={"session_id": sid, "sources": "hook,cognition", "limit": 20},
    )
    assert timeline_resp.status_code == 200
    events = timeline_resp.json()["data"]["events"]
    assert len(events) >= 2
    assert {"hook", "cognition"}.issubset({evt["source"] for evt in events})
