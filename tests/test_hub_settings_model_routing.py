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
        "mode": "explicit",
        "complexity_threshold": "COMPLICATED",
        "fallback_policy": "fail_closed",
        "max_parallel": 3,
        "orchestrator": {"adapter": "", "model": "", "effort": ""},
        "roles": {},
        "cooldown": {"default_seconds": 300, "maximum_seconds": 3600},
    }


def test_model_routing_patch_round_trips(client, tmp_path):
    body = {"model_routing": {"enabled": True, "orchestrator_model": "claude-haiku-4-5"}}
    patched = client.patch("/api/settings", json=body).json()["data"]
    assert patched["settings"]["model_routing"]["enabled"] is True
    assert patched["settings"]["model_routing"]["orchestrator_model"] == "claude-haiku-4-5"

    fetched = client.get("/api/settings").json()["data"]
    assert fetched["settings"]["model_routing"]["enabled"] is True
    assert fetched["settings"]["model_routing"]["orchestrator_model"] == "claude-haiku-4-5"

    on_disk = json.loads((tmp_path / "hub-settings.json").read_text())
    assert on_disk["model_routing"]["orchestrator_model"] == "claude-haiku-4-5"


def test_model_routing_policy_round_trips(client):
    body = {
        "model_routing": {
            "enabled": True,
            "mode": "adaptive",
            "fallback_policy": "next_eligible",
            "max_parallel": 5,
            "orchestrator": {"adapter": "codex", "model": "gpt-5", "effort": "high"},
            "roles": {"reviewer": {"adapter": "claude", "model": "sonnet", "effort": "high"}},
            "cooldown": {"default_seconds": 60, "maximum_seconds": 900},
        }
    }

    response = client.patch("/api/settings", json=body)

    assert response.status_code == 200
    routing = response.json()["data"]["settings"]["model_routing"]
    assert routing["mode"] == "adaptive"
    assert routing["orchestrator_model"] == "gpt-5"
    assert routing["roles"]["reviewer"]["adapter"] == "claude"
    assert routing["cooldown"]["maximum_seconds"] == 900


def test_model_routing_rejects_invalid_concurrency(client):
    response = client.patch(
        "/api/settings",
        json={"model_routing": {"enabled": True, "max_parallel": 0}},
    )

    assert response.status_code == 422


def test_model_routing_nested_patch_preserves_existing_fields(client):
    client.patch(
        "/api/settings",
        json={
            "model_routing": {
                "enabled": True,
                "cooldown": {"default_seconds": 60, "maximum_seconds": 900},
                "roles": {"reviewer": {"adapter": "claude", "model": "sonnet"}},
            }
        },
    )

    response = client.patch(
        "/api/settings",
        json={
            "model_routing": {
                "enabled": True,
                "cooldown": {"maximum_seconds": 1200},
                "roles": {"reviewer": {"effort": "high"}},
            }
        },
    )

    routing = response.json()["data"]["settings"]["model_routing"]
    assert routing["cooldown"] == {"default_seconds": 60, "maximum_seconds": 1200}
    assert routing["roles"]["reviewer"] == {
        "adapter": "claude",
        "model": "sonnet",
        "effort": "high",
    }


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
    assert client.patch("/api/settings/modules/no-such", json={"enabled": False}).status_code == 404
    assert client.patch("/api/settings/modules/memory", json={"enabled": "yes"}).status_code == 400


class TestConfigSkillsExtras:
    def test_skills_listing_carries_extra_flag_and_patch_round_trips(
        self, module_client, tmp_path, monkeypatch
    ):
        client, project = module_client
        (project / ".coding-os.yaml").write_text(
            "version: 1\ntemplates: []\nextra_skills: []\n", encoding="utf-8"
        )
        listing = client.get("/api/config/skills")
        assert listing.status_code == 200
        payload = listing.json()
        assert all("extra" in row for row in payload["skills"]) or payload["skills"] == []

        import yaml as _yaml

        # redis is a CORE skill — it ships enabled and round-trips through the
        # `disabled_skills` opt-out list, NOT `extra_skills` (which is the
        # community opt-IN list). Disabling it adds to disabled_skills.
        disabled = client.patch("/api/config/skills/redis", json={"enabled": False})
        assert disabled.status_code == 200, disabled.text
        assert disabled.json()["data"]["provenance"] == "core"
        config = _yaml.safe_load((project / ".coding-os.yaml").read_text(encoding="utf-8"))
        assert "redis" in config["disabled_skills"]
        assert "redis" not in (config.get("extra_skills") or [])

        # re-enabling removes it from the opt-out list — full round-trip.
        restored = client.patch("/api/config/skills/redis", json={"enabled": True})
        assert restored.status_code == 200
        config = _yaml.safe_load((project / ".coding-os.yaml").read_text(encoding="utf-8"))
        assert "redis" not in (config.get("disabled_skills") or [])

    def test_patch_validation_and_unknown_skill(self, module_client):
        client, project = module_client
        (project / ".coding-os.yaml").write_text(
            "version: 1\ntemplates: []\nextra_skills: []\n", encoding="utf-8"
        )
        bad_body = client.patch("/api/config/skills/redis", json={"enabled": "yes"})
        assert bad_body.status_code == 400
        unknown = client.patch("/api/config/skills/no-such", json={"enabled": True})
        assert unknown.status_code == 404
