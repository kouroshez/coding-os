"""Settings contract for claude_auth (TASK-756): default-off, masked reads,
exclude-unset key preservation, explicit-empty clear, and file permissions.
Spec: docs/adapters/claude-sdk.md § 7.6.
"""

from __future__ import annotations

import json
import stat
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


def test_claude_auth_defaults_subscription_unmasked(client):
    payload = client.get("/api/settings").json()["data"]
    assert payload["settings"]["claude_auth"] == {
        "mode": "subscription",
        "api_key_set": False,
        "api_key_preview": "",
    }


def test_claude_auth_patch_sets_key_and_masks_on_read(client, tmp_path):
    patched = client.patch(
        "/api/settings",
        json={"claude_auth": {"mode": "api_key", "api_key": "sk-ant-abcd1234"}},
    ).json()["data"]
    # PATCH response never echoes the raw key back
    assert patched["settings"]["claude_auth"] == {
        "mode": "api_key",
        "api_key_set": True,
        "api_key_preview": "...1234",
    }
    fetched = client.get("/api/settings").json()["data"]
    assert fetched["settings"]["claude_auth"] == patched["settings"]["claude_auth"]

    on_disk = json.loads((tmp_path / "hub-settings.json").read_text())
    assert on_disk["claude_auth"] == {"mode": "api_key", "api_key": "sk-ant-abcd1234"}


def test_claude_auth_patch_omitting_key_preserves_stored_value(client):
    client.patch(
        "/api/settings",
        json={"claude_auth": {"mode": "api_key", "api_key": "sk-ant-keepme01"}},
    )
    # Flip mode only — api_key field omitted entirely (not null, not "").
    patched = client.patch("/api/settings", json={"claude_auth": {"mode": "subscription"}}).json()[
        "data"
    ]
    assert patched["settings"]["claude_auth"]["mode"] == "subscription"
    assert patched["settings"]["claude_auth"]["api_key_set"] is True
    assert patched["settings"]["claude_auth"]["api_key_preview"] == "...me01"


def test_claude_auth_patch_explicit_empty_clears_key(client):
    client.patch(
        "/api/settings",
        json={"claude_auth": {"mode": "api_key", "api_key": "sk-ant-clearme0"}},
    )
    patched = client.patch(
        "/api/settings", json={"claude_auth": {"mode": "api_key", "api_key": ""}}
    ).json()["data"]
    assert patched["settings"]["claude_auth"] == {
        "mode": "api_key",
        "api_key_set": False,
        "api_key_preview": "",
    }


def test_hub_settings_file_is_owner_only_after_write(client, tmp_path):
    client.patch(
        "/api/settings",
        json={"claude_auth": {"mode": "api_key", "api_key": "sk-ant-permcheck"}},
    )
    mode = stat.S_IMODE((tmp_path / "hub-settings.json").stat().st_mode)
    assert mode == 0o600
