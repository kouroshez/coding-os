"""Guards for POST /api/logs/client — the browser-error beacon into logging_os.

The endpoint lets the SPA report uncaught errors / failed streams to the same
cos.log.jsonl sink as the server, so nothing in the UI fails silently.
"""

from __future__ import annotations

import logging
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


def _patch_client_logger(monkeypatch):
    """Spy on the module's client logger across either import path."""
    calls: list = []
    patched = False
    for modname in ("web.routes.logs", "core.web.routes.logs"):
        mod = sys.modules.get(modname)
        if mod is not None:
            monkeypatch.setattr(
                mod._client_logger, "log", lambda *a, **k: calls.append(a), raising=True
            )
            patched = True
    assert patched, "logs module not loaded"
    return calls


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


def test_client_log_emits_into_logging_sink(client, monkeypatch):
    """The beacon must actually reach the stdlib logger logging_os bridges —
    never a silent drop. Level maps from the client payload."""
    calls = _patch_client_logger(monkeypatch)
    client.post("/api/logs/client", json={"message": "kaboom", "level": "warn"})
    assert calls, "client logger was not called"
    assert calls[0][0] == logging.WARNING


def test_client_log_bounds_oversize_message(client, monkeypatch):
    """An oversize beacon must be truncated, never stored unbounded."""
    calls = _patch_client_logger(monkeypatch)
    client.post("/api/logs/client", json={"message": "x" * 9000})
    assert calls
    # call args: (level, fmt, message, url, context) — message is the 3rd.
    assert len(calls[0][2]) <= 2000


def test_client_log_unknown_level_defaults_to_error(client, monkeypatch):
    calls = _patch_client_logger(monkeypatch)
    client.post("/api/logs/client", json={"message": "x", "level": "bogus"})
    assert calls and calls[0][0] == logging.ERROR
