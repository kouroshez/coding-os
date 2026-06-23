"""Settings contract for git_settings (pr-mode, TASK-518):
default-off, PATCH round-trip, foreign-section preservation, and the
read-only git-state capability endpoint. Mirrors test_hub_settings_model_routing.
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


def test_git_settings_defaults_off(client):
    payload = client.get("/api/settings").json()["data"]
    assert payload["settings"]["git_settings"] == {
        "enabled": False,
        "integration_branch": "main",
        "protected_branches": ["production"],
    }


def test_git_settings_patch_round_trips(client, tmp_path):
    body = {
        "git_settings": {
            "enabled": True,
            "integration_branch": "develop",
            "protected_branches": ["production", "release"],
        }
    }
    patched = client.patch("/api/settings", json=body).json()["data"]
    assert patched["settings"]["git_settings"]["enabled"] is True
    assert patched["settings"]["git_settings"]["integration_branch"] == "develop"

    fetched = client.get("/api/settings").json()["data"]
    assert fetched["settings"]["git_settings"] == body["git_settings"]

    on_disk = json.loads((tmp_path / "hub-settings.json").read_text())
    assert on_disk["git_settings"] == body["git_settings"]


def test_git_settings_patch_leaves_other_sections(client):
    before = client.get("/api/settings").json()["data"]["settings"]
    client.patch("/api/settings", json={"git_settings": {"enabled": True}})
    after = client.get("/api/settings").json()["data"]["settings"]
    assert after["budget_cap"] == before["budget_cap"]
    assert after["model_routing"] == before["model_routing"]


def test_git_state_endpoint_reports_capability(client):
    # No git repo at the project root => not pr_ok; the endpoint must still
    # answer (degrade signal), never 500.
    resp = client.get("/api/settings/git-state")
    assert resp.status_code in (200, 503)
    if resp.status_code == 200:
        cap = resp.json()["data"]
        assert set(cap) >= {"remote", "gh", "required_check", "pr_ok", "missing"}
