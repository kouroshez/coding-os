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
        "autonomy_level": "draft",
    }


def test_git_settings_patch_round_trips(client, tmp_path):
    body = {
        "git_settings": {
            "enabled": True,
            "integration_branch": "develop",
            "protected_branches": ["production", "release"],
            "autonomy_level": "auto_merge",
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


def test_git_settings_partial_patch_preserves_own_fields(client):
    # finding 12: a partial PATCH MERGES — it must not reset unspecified
    # git_settings fields to their model defaults.
    client.patch(
        "/api/settings",
        json={
            "git_settings": {
                "enabled": True,
                "integration_branch": "develop",
                "protected_branches": ["prod", "release"],
            }
        },
    )
    # second PATCH touches only `enabled`; integration_branch + protected must survive
    client.patch("/api/settings", json={"git_settings": {"enabled": False}})
    gs = client.get("/api/settings").json()["data"]["settings"]["git_settings"]
    assert gs["enabled"] is False
    assert gs["integration_branch"] == "develop"
    assert gs["protected_branches"] == ["prod", "release"]


def test_git_settings_autonomy_level_defaults_draft_and_round_trips(client):
    # TASK-533: safe default is draft; a partial PATCH of autonomy alone must
    # not wipe sibling fields, and the level persists.
    assert client.get("/api/settings").json()["data"]["settings"]["git_settings"][
        "autonomy_level"
    ] == "draft"
    client.patch(
        "/api/settings",
        json={"git_settings": {"enabled": True, "integration_branch": "develop"}},
    )
    # enabled is the one required field on the model; the merge preserves the
    # unspecified integration_branch via exclude_unset.
    client.patch("/api/settings", json={"git_settings": {"enabled": True, "autonomy_level": "autonomous"}})
    gs = client.get("/api/settings").json()["data"]["settings"]["git_settings"]
    assert gs["autonomy_level"] == "autonomous"
    assert gs["integration_branch"] == "develop"  # sibling survived the autonomy PATCH
    assert gs["enabled"] is True


def test_git_settings_local_rung_accepted_and_invalid_rejected(client):
    # TASK-540: `local` is the new lowest rung (agent never pushes); the Literal
    # on _GitSettingsIn accepts it and rejects a typo'd rung at the API edge so a
    # bad value never reaches cos-env → COS_GIT_AUTONOMY.
    ok = client.patch("/api/settings", json={"git_settings": {"enabled": True, "autonomy_level": "local"}})
    assert ok.status_code == 200, ok.text
    assert ok.json()["data"]["settings"]["git_settings"]["autonomy_level"] == "local"
    bad = client.patch("/api/settings", json={"git_settings": {"enabled": True, "autonomy_level": "yolo"}})
    assert bad.status_code == 422, bad.text


def test_git_state_endpoint_reports_capability(client):
    # No git repo at the project root => not pr_ok; the endpoint must still
    # answer (degrade signal), never 500.
    resp = client.get("/api/settings/git-state")
    assert resp.status_code in (200, 503)
    if resp.status_code == 200:
        cap = resp.json()["data"]
        assert set(cap) >= {"remote", "gh", "required_check", "pr_ok", "missing"}
        # TASK-534: real git-state keys are merged in alongside the capability probe
        assert set(cap) >= {"branches", "current_branch", "remote_url"}
        assert isinstance(cap["branches"], list)


def test_git_state_probes_query_param_branch(client, monkeypatch):
    # TASK-549/M2: ?integration=<x> must reach _preflight so the capability pills
    # reflect the branch the user is editing, not the saved one. Stub _preflight +
    # _git_state so the probe runs without a real repo/gh and capture the branch.
    import cli.pr_commands as pr

    seen: dict = {}

    def fake_preflight(repo, integration):
        seen["integration"] = integration
        return {"remote": True, "gh": True, "required_check": True, "pr_ok": True, "missing": []}

    monkeypatch.setattr(pr, "_preflight", fake_preflight)
    monkeypatch.setattr(
        pr, "_git_state", lambda repo: {"branches": [], "current_branch": "", "remote_url": ""}
    )

    assert client.get("/api/settings/git-state?integration=develop").status_code == 200
    assert seen["integration"] == "develop"
    # Absent param falls back to the saved/default branch (not the query value).
    seen.clear()
    monkeypatch.setattr(pr, "_integration_branch", lambda repo: "main")
    assert client.get("/api/settings/git-state").status_code == 200
    assert seen["integration"] == "main"
