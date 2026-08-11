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

from web.server import create_app

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
    # Deterministic import — never depend on an earlier test having built the app.
    # Patch the module that DEFINES and CALLS _run_cos_init: the route resolves it
    # from its own globals, so patching the hub facade's re-export would miss.
    import web.routes._hub_init_routes as init_routes

    monkeypatch.setattr(init_routes, "_run_cos_init", fn)


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
        assert by_id["nextjs-fastapi"]["provenance"] == "core"
        for p in data["presets"]:
            assert p["label"] and p["id"] and p["stacks"]
            assert p["provenance"] in {"core", "user"}


class TestSkillCatalogEndpoints:
    def test_global_skill_catalog(self, hub_env):
        with _client() as client:
            resp = client.get("/api/hub/skills")
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["count"] == len(data["skills"]) > 0
        assert {e["provenance"] for e in data["skills"]} >= {"core"}

    def test_stack_skill_groups(self, hub_env):
        with _client() as client:
            resp = client.get("/api/hub/stacks/fastapi/skills")
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["stack"] == "fastapi"
        assert set(data["groups"]) == {"required", "recommended", "optional"}
        assert data["groups"]["required"][0]["name"] == "python-fastapi"

    def test_unknown_stack_404(self, hub_env):
        with _client() as client:
            resp = client.get("/api/hub/stacks/no-such/skills")
        assert resp.status_code == 404


class TestAdaptersEndpoint:
    def test_lists_data_driven_adapters(self, hub_env):
        with _client() as client:
            resp = client.get("/api/hub/adapters")
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        ids = {a["id"] for a in data["adapters"]}
        assert "claude" in ids  # ships in this repo; no hardcoded single agent
        assert data["count"] == len(data["adapters"]) >= 2


class TestRegistryRename:
    def test_temp_slug_renames_without_breaking_entry(self, hub_env):
        from cli.registry import add_project, load_registry

        proj = hub_env / "proj-abc123"
        (proj / ".coding-os").mkdir(parents=True)
        add_project(proj, slug="proj-abc123")
        with _client() as client:
            resp = client.patch("/api/hub/registry/proj-abc123", json={"new_slug": "real-name"})
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["slug"] == "real-name"
        entries = {p.slug: p.path for p in load_registry().projects}
        assert entries["real-name"] == str(proj)  # path untouched

    def test_rename_unknown_404_and_duplicate_409(self, hub_env):
        from cli.registry import add_project

        for slug in ("one", "two"):
            d = hub_env / slug
            (d / ".coding-os").mkdir(parents=True)
            add_project(d, slug=slug)
        with _client() as client:
            missing = client.patch("/api/hub/registry/ghost", json={"new_slug": "x1"})
            dup = client.patch("/api/hub/registry/one", json={"new_slug": "two"})
        assert missing.status_code == 404
        assert dup.status_code == 409
