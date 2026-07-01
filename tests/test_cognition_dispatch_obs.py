"""TASK-667 — dispatch observability: trace SSE stream + dead-modal transcript fallback."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_REPO_ROOT = Path(__file__).resolve().parent.parent
for _p in (_REPO_ROOT, _REPO_ROOT / "src" / "core"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from core.web.routes import cognition
from core.web.server import create_app


def _make_dispatch_db(tmp_path: Path, sub_session_id: str, transcript: str) -> str:
    db = tmp_path / "coding-os.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE formula_dispatches "
        "(sub_session_id TEXT, formula_id TEXT, status TEXT, model TEXT, "
        "raw_transcript TEXT, ts TEXT)"
    )
    conn.execute(
        "INSERT INTO formula_dispatches VALUES (?,?,?,?,?,?)",
        (sub_session_id, "implementer", "ok", "claude-opus-4-8", transcript, "2026-07-01T00:00:00Z"),
    )
    conn.commit()
    conn.close()
    return str(db)


def test_dispatch_transcript_chat_returns_persisted(tmp_path, monkeypatch):
    db = _make_dispatch_db(tmp_path, "ses-sdk-1", "hello from the dispatched agent")
    monkeypatch.setattr(cognition, "_db_path", lambda: db)
    result = cognition._dispatch_transcript_chat("ses-sdk-1")
    assert result is not None
    assert result["session"]["source"] == "dispatch_transcript"
    assert result["messages"][0]["blocks"][0]["text"] == "hello from the dispatched agent"
    assert result["meta"]["source"] == "formula_dispatches"


def test_dispatch_transcript_chat_none_when_absent(tmp_path, monkeypatch):
    db = _make_dispatch_db(tmp_path, "ses-sdk-1", "x")
    monkeypatch.setattr(cognition, "_db_path", lambda: db)
    assert cognition._dispatch_transcript_chat("ses-nope") is None


def test_get_chat_falls_back_to_transcript(tmp_path, monkeypatch):
    # COS_DB_PATH is resolved at request time by _db_path(), so it works
    # regardless of which module instance the app registered (avoids the
    # dual-import patch trap). "ses-sdk-2" is not a live SDK chat session, so
    # get_session_info returns None → the route yields to the dispatch fallback.
    db = _make_dispatch_db(tmp_path, "ses-sdk-2", "dispatched transcript body")
    monkeypatch.setenv("COS_DB_PATH", db)
    with TestClient(create_app()) as c:
        r = c.get("/api/cognition/chat/ses-sdk-2")
    resp = r.json()
    if resp.get("ok") is False and resp.get("error", {}).get("category") == "unavailable":
        pytest.skip("claude-agent-sdk not installed — live-session path can't reach the fallback here")
    assert r.status_code == 200
    data = resp["data"]
    assert data["session"]["source"] == "dispatch_transcript"
    assert "dispatched transcript body" in data["messages"][0]["blocks"][0]["text"]


def test_drain_trace_events_reads_and_tails(tmp_path):
    # The SSE loop's tail helper: replay from 0, then only new lines after pos.
    log = tmp_path / "ses-sdk-3.jsonl"
    log.write_text(
        json.dumps({"kind": "dispatch_started", "data": {}})
        + "\n"
        + json.dumps({"kind": "dispatch_turn", "data": {"seq": 1}})
        + "\n",
        encoding="utf-8",
    )
    events, pos = cognition._drain_trace_events(log, 0)
    assert [e["kind"] for e in events] == ["dispatch_started", "dispatch_turn"]
    assert pos > 0

    # No new bytes → nothing to emit, position unchanged.
    events2, pos2 = cognition._drain_trace_events(log, pos)
    assert events2 == []
    assert pos2 == pos

    # Append one more event → only the new line is drained.
    with log.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"kind": "dispatch_completed", "data": {"turns": 1}}) + "\n")
    events3, _ = cognition._drain_trace_events(log, pos)
    assert [e["kind"] for e in events3] == ["dispatch_completed"]


def test_drain_trace_events_missing_file(tmp_path):
    events, pos = cognition._drain_trace_events(tmp_path / "nope.jsonl", 0)
    assert events == []
    assert pos == 0


def test_stream_trace_route_registered():
    app = create_app()
    paths = {getattr(r, "path", "") for r in app.routes}
    assert "/api/cognition/trace/{session_id}/stream" in paths
