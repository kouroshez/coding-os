"""Pytest coverage for /api/observability endpoints."""

from __future__ import annotations

import json
import sys
import time
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
    (state / "claude" / "traces").mkdir(parents=True)
    (state / "claude" / "sessions").mkdir(parents=True)
    monkeypatch.setenv("COS_STATE_DIR", str(state))
    monkeypatch.setenv("COS_HOOK_LOG", str(state / ".hooks.log"))
    app = create_app()
    with TestClient(app) as c:
        yield c, state


def test_observability_sessions_lists_unified_rows(client):
    c, state = client
    sid = "ses-claude-20260425-170000-abcd"
    (state / "claude" / "traces" / f"{sid}.jsonl").write_text("{}", encoding="utf-8")
    (state / "claude" / "sessions" / f"{sid}.json").write_text(
        json.dumps({"session_id": sid, "started_at": time.time(), "last_tool_at": time.time()}),
        encoding="utf-8",
    )

    resp = c.get("/api/observability/sessions")
    assert resp.status_code == 200
    payload = resp.json()["data"]
    assert payload["count"] >= 1
    row = next(r for r in payload["sessions"] if r["session_id"] == sid)
    assert row["source"] == "trace+session"
    assert row["has_trace"] is True
    assert "display_name" in row


def test_observability_timeline_merges_hook_and_cognition(client):
    c, state = client
    sid = "ses-claude-20260425-171500-efgh"
    now = time.time()
    (state / "claude" / "traces" / f"{sid}.jsonl").write_text(
        json.dumps({"kind": "compose_done", "ts": now, "agent": "claude"}) + "\n",
        encoding="utf-8",
    )
    (state / ".hooks.log").write_text(
        "[2026-04-25T17:15:10Z] [session-context] [fire] "
        f"agent=claude session={sid} task=TASK-126 detail=started\n",
        encoding="utf-8",
    )

    resp = c.get("/api/observability/timeline", params={"session_id": sid, "limit": 50})
    assert resp.status_code == 200
    payload = resp.json()["data"]
    assert payload["count"] >= 2
    sources = {row["source"] for row in payload["events"]}
    assert "hook" in sources
    assert "cognition" in sources


def test_observability_timeline_source_filter(client):
    c, state = client
    sid = "ses-claude-20260425-172000-ijkl"
    (state / "claude" / "traces" / f"{sid}.jsonl").write_text(
        json.dumps({"kind": "analyze_done", "ts": time.time(), "agent": "claude"}) + "\n",
        encoding="utf-8",
    )
    (state / ".hooks.log").write_text(
        "[2026-04-25T17:20:10Z] [capture-observation] [fire] "
        f"agent=claude session={sid} task=TASK-126 detail=write\n",
        encoding="utf-8",
    )

    resp = c.get(
        "/api/observability/timeline",
        params={"session_id": sid, "sources": "hook", "limit": 50},
    )
    assert resp.status_code == 200
    events = resp.json()["data"]["events"]
    assert events
    assert all(evt["source"] == "hook" for evt in events)
