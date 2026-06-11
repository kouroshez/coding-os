"""TASK-249 — GET /api/hub/stacks + POST /api/hub/registry/init (create-from-UI).

The real scaffold is covered by tests/test_cli.py; here we cover the data-driven
stack list and the route's validation + cleanup contract with _run_cos_init mocked.
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

from web.server import create_app  # noqa: E402

_LOCAL = "http://localhost:9188"


@pytest.fixture
def hub_env(tmp_path, monkeypatch):
    monkeypatch.setenv("COS_REGISTRY_PATH", str(tmp_path / "registry.json"))
    monkeypatch.delenv("COS_WEB_CORS_ALLOW_ALL", raising=False)
    return tmp_path


def _client() -> TestClient:
    # localhost base_url so the security gate's Host check passes for mutations.
    return TestClient(create_app(), base_url=_LOCAL)


def _patch_init(monkeypatch, fn):
    patched = False
    for modname in ("web.routes.hub", "core.web.routes.hub"):
        mod = sys.modules.get(modname)
        if mod is not None:
            monkeypatch.setattr(mod, "_run_cos_init", fn, raising=False)
            patched = True
    assert patched, "hub route module not loaded"


class TestStacksEndpoint:
    def test_lists_data_driven_stacks(self, hub_env):
        with _client() as client:
            resp = client.get("/api/hub/stacks")
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        ids = {s["id"] for s in data["stacks"]}
        assert data["count"] == len(data["stacks"]) > 0
        assert "_base" not in ids  # the base profile is not an installable stack
        assert "meta" in ids  # the meta stack ships in this repo
        for s in data["stacks"]:
            assert s["label"] and s["id"]


class TestPresetsEndpoint:
    def test_lists_data_driven_presets(self, hub_env):
        with _client() as client:
            resp = client.get("/api/hub/presets")
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["count"] == len(data["presets"]) > 0
        by_id = {p["id"]: p for p in data["presets"]}
        assert by_id["nextjs-fastapi"]["stacks"] == ["nextjs", "fastapi"]
        for p in data["presets"]:
            assert p["label"] and p["id"] and p["stacks"]


class TestInitRouteValidation:
    def test_bad_name_rejected(self, hub_env):
        with _client() as client:
            resp = client.post(
                "/api/hub/registry/init",
                json={"name": "Bad Name!", "parent_dir": str(hub_env)},
            )
        assert resp.status_code == 400
        assert resp.json()["error"]["category"] == "validation"

    def test_missing_parent_dir_rejected(self, hub_env):
        with _client() as client:
            resp = client.post("/api/hub/registry/init", json={"name": "proj", "parent_dir": "  "})
        assert resp.status_code == 400

    def test_parent_not_a_dir(self, hub_env):
        with _client() as client:
            resp = client.post(
                "/api/hub/registry/init",
                json={"name": "proj", "parent_dir": str(hub_env / "nope")},
            )
        assert resp.status_code == 404

    def test_target_already_exists(self, hub_env):
        (hub_env / "proj").mkdir()
        with _client() as client:
            resp = client.post(
                "/api/hub/registry/init",
                json={"name": "proj", "parent_dir": str(hub_env)},
            )
        assert resp.status_code == 409

    def test_refuses_meta_repo_parent(self, hub_env):
        with _client() as client:
            resp = client.post(
                "/api/hub/registry/init",
                json={"name": "proj", "parent_dir": str(_REPO_ROOT)},
            )
        assert resp.status_code == 400
        assert "meta-repo" in resp.json()["error"]["message"]


class TestInitRouteRun:
    def test_happy_path_returns_slug(self, hub_env, monkeypatch):
        _patch_init(monkeypatch, lambda *a, **k: (True, {"slug": "proj"}, ""))
        with _client() as client:
            resp = client.post(
                "/api/hub/registry/init",
                json={"name": "proj", "parent_dir": str(hub_env), "stack": "python"},
            )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["slug"] == "proj"

    def test_failed_init_cleans_up_partial_scaffold(self, hub_env, monkeypatch):
        # Simulate init creating a partial dir then failing — the route must rmtree it.
        def _fake(name, parent_dir, stack, agent, timeout=180):
            (Path(parent_dir) / name).mkdir(parents=True, exist_ok=True)
            return (False, None, "boom")

        _patch_init(monkeypatch, _fake)
        with _client() as client:
            resp = client.post(
                "/api/hub/registry/init",
                json={"name": "halfbaked", "parent_dir": str(hub_env)},
            )
        assert resp.status_code == 500
        assert not (hub_env / "halfbaked").exists()  # partial scaffold removed
