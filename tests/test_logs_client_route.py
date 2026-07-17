"""Guards for POST /api/logs/client — the browser-error beacon into logging_os.

The endpoint lets the SPA report uncaught errors / failed streams to the same
cos.log.jsonl sink as the server, so nothing in the UI fails silently.
"""

from __future__ import annotations

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
    state.mkdir(parents=True)
    monkeypatch.setenv("COS_STATE_DIR", str(state))
    with TestClient(create_app()) as c:
        yield c


def _recent_msgs(client, level="debug") -> list[dict]:
    r = client.get(f"/api/logs/recent?level={level}")
    assert r.status_code == 200
    return r.json()["data"]["events"]


def test_client_log_requires_message(client):
    r = client.post("/api/logs/client", json={"level": "error"})
    assert r.json()["error"]["category"] == "validation"


def test_client_log_records_ok(client):
    r = client.post(
        "/api/logs/client",
        json={"level": "error", "message": "boom", "url": "http://x/y", "context": {"a": 1}},
    )
    body = r.json()
    assert body["data"]["recorded"] is True
    # unwrap() hoists meta to the envelope top level.
    assert body["meta"]["source"] == "client"


def test_client_log_lands_in_the_readable_sink(client):
    """The beacon must reach the SAME sink the GET readers serve (scoped write),
    never a silent drop — client + server share one per-project timeline."""
    client.post("/api/logs/client", json={"message": "kaboom-beacon", "level": "warn"})
    events = _recent_msgs(client)
    beacon = next((e for e in events if "kaboom-beacon" in str(e.get("msg", ""))), None)
    assert beacon is not None, "client beacon did not reach the readable sink"
    assert beacon["lvl"] == "WARN"
    assert beacon["scope"] == "coding_os.web.client"


def test_client_log_bounds_oversize_message(client):
    """An oversize beacon must be truncated, never stored unbounded."""
    client.post("/api/logs/client", json={"message": "z" * 9000})
    events = _recent_msgs(client)
    beacon = next((e for e in events if str(e.get("scope")) == "coding_os.web.client"), None)
    assert beacon is not None
    # The bounded message is ≤2000 chars; the msg field adds only a short prefix.
    assert len(str(beacon["msg"])) <= 2100


def test_client_log_unknown_level_defaults_to_error(client):
    client.post("/api/logs/client", json={"message": "levelcheck", "level": "bogus"})
    events = _recent_msgs(client)
    beacon = next((e for e in events if "levelcheck" in str(e.get("msg", ""))), None)
    assert beacon is not None and beacon["lvl"] == "ERROR"
