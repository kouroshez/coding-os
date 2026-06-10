"""Settings contract for model_routing (TASK-317):
default-off, PATCH round-trip, and foreign-section preservation.
Spec: docs/engineering/hub-architecture.md § Hub settings contract.
"""

from __future__ import annotations

import json
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
    monkeypatch.setenv("COS_STATE_DIR", str(tmp_path))
    return TestClient(create_app())


def test_model_routing_defaults_off(client):
    payload = client.get("/api/settings").json()["data"]
    assert payload["settings"]["model_routing"] == {
        "enabled": False,
        "orchestrator_model": "",
    }


def test_model_routing_patch_round_trips(client, tmp_path):
    body = {"model_routing": {"enabled": True, "orchestrator_model": "claude-haiku-4-5"}}
    patched = client.patch("/api/settings", json=body).json()["data"]
    assert patched["settings"]["model_routing"]["enabled"] is True
    assert patched["settings"]["model_routing"]["orchestrator_model"] == "claude-haiku-4-5"

    fetched = client.get("/api/settings").json()["data"]
    assert fetched["settings"]["model_routing"] == body["model_routing"]

    on_disk = json.loads((tmp_path / "hub-settings.json").read_text())
    assert on_disk["model_routing"] == body["model_routing"]


def test_model_routing_patch_leaves_other_sections(client):
    before = client.get("/api/settings").json()["data"]["settings"]
    client.patch(
        "/api/settings",
        json={"model_routing": {"enabled": True, "orchestrator_model": ""}},
    )
    after = client.get("/api/settings").json()["data"]["settings"]
    assert after["budget_cap"] == before["budget_cap"]
    assert after["trace_rotation"] == before["trace_rotation"]
