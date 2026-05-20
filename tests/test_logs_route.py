"""Pytest coverage for /api/logs endpoints."""

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
    state.mkdir(parents=True)
    monkeypatch.setenv("COS_STATE_DIR", str(state))
    monkeypatch.setenv("COS_HOOK_LOG", str(state / ".hooks.log"))
    monkeypatch.setenv("COS_LOG_FILE", str(state / ".cos.log"))
    monkeypatch.delenv("COS_LOG_JSON", raising=False)
    app = create_app()
    with TestClient(app) as c:
        yield c, state


def _seed_jsonl(state, events):
    path = state / ".cos.log.jsonl"
    with path.open("w", encoding="utf-8") as handle:
        for evt in events:
            handle.write(json.dumps(evt) + "\n")


def test_recent_returns_all_when_no_filter(client):
    c, state = client
    _seed_jsonl(
        state,
        [
            {"ts": "2026-05-15T12:00:00Z", "lvl": "INFO", "scope": "cli.a", "msg": "info"},
            {"ts": "2026-05-15T12:00:01Z", "lvl": "WARN", "scope": "hook.b", "msg": "warn"},
        ],
    )
    resp = c.get("/api/logs/recent")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["count"] == 2
    assert [evt["lvl"] for evt in data["events"]] == ["INFO", "WARN"]


def test_recent_level_floor_drops_below(client):
    c, state = client
    _seed_jsonl(
        state,
        [
            {"ts": "2026-05-15T12:00:00Z", "lvl": "DEBUG", "scope": "x.y", "msg": "d"},
            {"ts": "2026-05-15T12:00:01Z", "lvl": "INFO", "scope": "x.y", "msg": "i"},
            {"ts": "2026-05-15T12:00:02Z", "lvl": "WARN", "scope": "x.y", "msg": "w"},
            {"ts": "2026-05-15T12:00:03Z", "lvl": "ERROR", "scope": "x.y", "msg": "e"},
        ],
    )
    resp = c.get("/api/logs/recent", params={"level": "warn"})
    data = resp.json()["data"]
    assert [evt["lvl"] for evt in data["events"]] == ["WARN", "ERROR"]


def test_recent_scope_glob_filter(client):
    c, state = client
    _seed_jsonl(
        state,
        [
            {"ts": "2026-05-15T12:00:00Z", "lvl": "INFO", "scope": "hook.foo", "msg": "1"},
            {"ts": "2026-05-15T12:00:01Z", "lvl": "INFO", "scope": "hook.bar", "msg": "2"},
            {"ts": "2026-05-15T12:00:02Z", "lvl": "INFO", "scope": "cli.doctor", "msg": "3"},
        ],
    )
    resp = c.get("/api/logs/recent", params={"scope": "hook.*"})
    data = resp.json()["data"]
    assert sorted(evt["scope"] for evt in data["events"]) == ["hook.bar", "hook.foo"]


def test_recent_substring_search(client):
    c, state = client
    _seed_jsonl(
        state,
        [
            {"ts": "2026-05-15T12:00:00Z", "lvl": "INFO", "scope": "x.y", "msg": "match-me here"},
            {"ts": "2026-05-15T12:00:01Z", "lvl": "INFO", "scope": "x.y", "msg": "unrelated"},
        ],
    )
    resp = c.get("/api/logs/recent", params={"search": "match-me"})
    data = resp.json()["data"]
    assert data["count"] == 1
    assert data["events"][0]["msg"] == "match-me here"


def test_recent_limit_keeps_newest_tail(client):
    c, state = client
    _seed_jsonl(
        state,
        [
            {"ts": f"2026-05-15T12:00:{i:02d}Z", "lvl": "INFO", "scope": "x.y", "msg": f"m{i}"}
            for i in range(20)
        ],
    )
    resp = c.get("/api/logs/recent", params={"limit": 5})
    data = resp.json()["data"]
    assert data["count"] == 5
    assert [evt["msg"] for evt in data["events"]] == ["m15", "m16", "m17", "m18", "m19"]


def test_recent_missing_file_returns_empty(client):
    c, _state = client
    resp = c.get("/api/logs/recent")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["count"] == 0
    assert data["events"] == []


def test_recent_invalid_level_falls_back_to_debug(client):
    c, state = client
    _seed_jsonl(
        state,
        [
            {"ts": "2026-05-15T12:00:00Z", "lvl": "INFO", "scope": "x.y", "msg": "kept"},
        ],
    )
    resp = c.get("/api/logs/recent", params={"level": "garbage"})
    assert resp.status_code == 200
    assert resp.json()["data"]["count"] == 1


def test_recent_corrupt_json_lines_skipped(client):
    c, state = client
    path = state / ".cos.log.jsonl"
    path.write_text(
        '{"ts":"2026-05-15T12:00:00Z","lvl":"INFO","scope":"x.y","msg":"ok"}\n'
        "not-valid-json\n"
        '{"ts":"2026-05-15T12:00:01Z","lvl":"WARN","scope":"x.y","msg":"also-ok"}\n',
        encoding="utf-8",
    )
    data = c.get("/api/logs/recent").json()["data"]
    assert data["count"] == 2
    assert [evt["lvl"] for evt in data["events"]] == ["INFO", "WARN"]


def test_stream_route_is_registered(client):
    c, _state = client
    routes = {getattr(r, "path", "") for r in c.app.routes}
    assert "/api/logs/stream" in routes
    assert "/api/logs/recent" in routes
