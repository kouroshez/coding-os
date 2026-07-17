"""Pytest coverage for /api/sessions/active (presence read API).

Locks the TASK-833 hardening: SSOT-derived TTL, a field allow-list (no host
paths / internal fields leaked), and the standard {data, meta} envelope.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_REPO_ROOT = Path(__file__).resolve().parent.parent
for _p in (_REPO_ROOT, _REPO_ROOT / "src" / "core"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from core.board_os.presence import PRESENT_WINDOW_SECS
from core.web.server import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    state = tmp_path / ".coding-os"
    (state / "claude" / "sessions").mkdir(parents=True)
    monkeypatch.setenv("COS_STATE_DIR", str(state))
    app = create_app()
    with TestClient(app) as c:
        yield c, state


def _write_presence(state: Path, sid: str, **extra) -> None:
    agent = state / "claude"
    (agent / "session-id").write_text(sid, encoding="utf-8")
    rec = {
        "session_id": sid,
        "agent": "claude",
        "pid": os.getpid(),
        "model": "opus",
        "last_tool_at": int(time.time()),
        "started_at": int(time.time()),
    }
    rec.update(extra)
    (agent / "sessions" / f"{sid}.json").write_text(json.dumps(rec), encoding="utf-8")


def test_sessions_active_uses_ssot_ttl_and_hides_host_paths(client):
    c, state = client
    _write_presence(
        state,
        "ses-claude-20260717-000000-aaaa",
        presence_file="/Users/secret/abs/path.json",
        internal_secret="LEAK_ME",
    )
    r = c.get("/api/sessions/active")
    assert r.status_code == 200
    body = r.json()

    # Standard {data, meta} envelope — not the legacy {ok, data}.
    assert "data" in body
    assert body.get("meta", {}).get("layer") == "observability"
    data = body["data"]

    # TTL is the board_os.presence SSOT window, not the old hardcoded 300.
    assert data["ttl_s"] == PRESENT_WINDOW_SECS
    # No absolute host path leaks in the payload.
    assert "state_dir" not in data
    assert "LEAK_ME" not in r.text

    assert data["sessions"], "expected the live session in the payload"
    rec = data["sessions"][0]
    assert "presence_file" not in rec
    assert "internal_secret" not in rec
    assert rec["session_id"] == "ses-claude-20260717-000000-aaaa"
    assert rec["state"] in {"active", "present", "idle", "offline", "ended"}


def test_sessions_active_empty_state_returns_clean_envelope(client):
    c, state = client
    # Remove the sessions dir so the state dir has no agent presence.
    for child in (state / "claude").glob("*"):
        if child.is_dir():
            for f in child.glob("*"):
                f.unlink()
            child.rmdir()
    r = c.get("/api/sessions/active")
    assert r.status_code == 200
    body = r.json()
    assert body["data"]["sessions"] == []
    assert body.get("meta", {}).get("layer") == "observability"
