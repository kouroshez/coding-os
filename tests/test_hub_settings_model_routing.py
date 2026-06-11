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


# ---------------------------------------------------------------------------
# Module toggle settings API — TASK-354
# ---------------------------------------------------------------------------


@pytest.fixture
def module_client(tmp_path, monkeypatch):
    """Client bound to a minimal fake project (no full init needed — the
    module API only touches subsystems-state.json + skips regen gracefully)."""
    project = tmp_path / "proj"
    (project / ".coding-os").mkdir(parents=True)
    monkeypatch.setenv("COS_PROJECT_ROOT", str(project))
    monkeypatch.setenv("COS_STATE_DIR", str(project / ".coding-os"))
    monkeypatch.chdir(project)
    return TestClient(create_app(), base_url="http://localhost:9188"), project


def test_modules_listed_with_kernel_locked(module_client):
    client, _ = module_client
    payload = client.get("/api/settings/modules").json()["data"]
    by_id = {m["id"]: m for m in payload["modules"]}
    assert by_id["kernel"]["kernel"] is True and by_id["kernel"]["enabled"] is True
    assert by_id["tasks"]["depends_on"] == ["docs"]
    assert all(m["enabled"] for m in payload["modules"])  # default all-on


def test_toggle_persists_and_reload_reflects(module_client):
    client, project = module_client
    resp = client.patch("/api/settings/modules/memory", json={"enabled": False})
    assert resp.status_code == 200, resp.text
    state = json.loads(
        (project / ".coding-os" / "subsystems-state.json").read_text(encoding="utf-8")
    )
    assert state["disabled"] == ["memory"]
    reloaded = client.get("/api/settings/modules").json()["data"]
    assert {m["id"]: m["enabled"] for m in reloaded["modules"]}["memory"] is False


def test_kernel_toggle_refused(module_client):
    client, _ = module_client
    resp = client.patch("/api/settings/modules/kernel", json={"enabled": False})
    assert resp.status_code == 400
    assert "kernel" in resp.json()["error"]["message"]


def test_unknown_module_404_and_bad_body_400(module_client):
    client, _ = module_client
    assert client.patch(
        "/api/settings/modules/no-such", json={"enabled": False}
    ).status_code == 404
    assert client.patch(
        "/api/settings/modules/memory", json={"enabled": "yes"}
    ).status_code == 400
