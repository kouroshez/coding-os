"""Tests for /api/hub/registry/{add, remove, scan, gc} + /api/hub/suggest-roots."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from web.server import create_app


@pytest.fixture
def hub_env(tmp_path, monkeypatch):
    """Give each test an isolated registry + a fake cwd project."""
    registry = tmp_path / "registry.json"
    monkeypatch.setenv("COS_REGISTRY_PATH", str(registry))

    cwd_project = tmp_path / "meta"
    (cwd_project / ".coding-os").mkdir(parents=True)
    monkeypatch.setenv("COS_PROJECT_ROOT", str(cwd_project))
    monkeypatch.chdir(cwd_project)

    return {
        "tmp": tmp_path,
        "registry": registry,
        "cwd_project": cwd_project,
    }


def _client() -> TestClient:
    return TestClient(create_app())


def _make_project(root: Path, name: str) -> Path:
    p = root / name
    (p / ".coding-os").mkdir(parents=True)
    return p


# ---------------------------------------------------------------------------
# POST /api/hub/registry/add
# ---------------------------------------------------------------------------


class TestRegistryAdd:
    def test_add_existing_project(self, hub_env):
        proj = _make_project(hub_env["tmp"], "alpha")
        with _client() as client:
            resp = client.post("/api/hub/registry/add", json={"path": str(proj)})
        assert resp.status_code == 200, resp.text
        body = resp.json()["data"]
        assert body["slug"] == "alpha"
        assert Path(body["path"]) == proj.resolve()

    def test_add_rejects_missing_path(self, hub_env):
        with _client() as client:
            resp = client.post(
                "/api/hub/registry/add",
                json={"path": str(hub_env["tmp"] / "does-not-exist")},
            )
        assert resp.status_code == 404
        assert "not a directory" in resp.json()["error"]["message"]

    def test_add_rejects_non_cos_directory(self, hub_env, tmp_path):
        plain = tmp_path / "not-a-cos-project"
        plain.mkdir()
        with _client() as client:
            resp = client.post("/api/hub/registry/add", json={"path": str(plain)})
        assert resp.status_code == 400
        assert "no .coding-os" in resp.json()["error"]["message"]

    def test_add_rejects_empty_path(self, hub_env):
        with _client() as client:
            resp = client.post("/api/hub/registry/add", json={"path": "  "})
        assert resp.status_code == 400

    def test_add_is_idempotent_on_same_path(self, hub_env):
        proj = _make_project(hub_env["tmp"], "beta")
        with _client() as client:
            first = client.post("/api/hub/registry/add", json={"path": str(proj)}).json()
            second = client.post("/api/hub/registry/add", json={"path": str(proj)}).json()
        assert first["data"]["slug"] == second["data"]["slug"]

    def test_add_slug_collision_returns_validation_error(self, hub_env):
        a = _make_project(hub_env["tmp"] / "a", "proj")
        b = _make_project(hub_env["tmp"] / "b", "proj")
        with _client() as client:
            first = client.post("/api/hub/registry/add", json={"path": str(a)})
            assert first.status_code == 200
            second = client.post("/api/hub/registry/add", json={"path": str(b)})
        assert second.status_code == 400
        assert "already used" in second.json()["error"]["message"].lower()

    def test_add_honours_custom_slug(self, hub_env):
        proj = _make_project(hub_env["tmp"], "thing")
        with _client() as client:
            resp = client.post(
                "/api/hub/registry/add",
                json={"path": str(proj), "slug": "custom-slug"},
            )
        assert resp.status_code == 200
        assert resp.json()["data"]["slug"] == "custom-slug"


# ---------------------------------------------------------------------------
# DELETE /api/hub/registry/{slug}
# ---------------------------------------------------------------------------


class TestRegistryRemove:
    def test_remove_by_slug(self, hub_env):
        proj = _make_project(hub_env["tmp"], "gamma")
        with _client() as client:
            client.post("/api/hub/registry/add", json={"path": str(proj)})
            resp = client.delete("/api/hub/registry/gamma")
        assert resp.status_code == 200
        assert resp.json()["data"]["slug"] == "gamma"

        # Confirm it's gone from the list
        with _client() as client:
            listing = client.get("/api/hub/projects").json()
        slugs = [p["slug"] for p in listing["projects"]]
        assert "gamma" not in slugs

    def test_remove_unknown_slug_404(self, hub_env):
        with _client() as client:
            resp = client.delete("/api/hub/registry/no-such-slug")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/hub/registry/scan
# ---------------------------------------------------------------------------


class TestRegistryScan:
    def test_scan_finds_nested_projects(self, hub_env):
        root = hub_env["tmp"] / "workspace"
        root.mkdir()
        _make_project(root, "one")
        _make_project(root / "sub", "two")
        with _client() as client:
            resp = client.post(
                "/api/hub/registry/scan",
                json={"root": str(root), "max_depth": 4, "limit": 20},
            )
        body = resp.json()["data"]
        paths = {Path(h["path"]).name for h in body["hits"]}
        assert {"one", "two"} <= paths

    def test_scan_marks_already_registered(self, hub_env):
        proj = _make_project(hub_env["tmp"] / "ws", "hello")
        with _client() as client:
            client.post("/api/hub/registry/add", json={"path": str(proj)})
            resp = client.post(
                "/api/hub/registry/scan",
                json={"root": str(hub_env["tmp"] / "ws"), "max_depth": 2},
            )
        hits = resp.json()["data"]["hits"]
        assert any(h["already_registered"] and Path(h["path"]) == proj.resolve() for h in hits)

    def test_scan_skips_noise_directories(self, hub_env):
        root = hub_env["tmp"] / "mixed"
        root.mkdir()
        _make_project(root, "real")
        # Build noise dirs that each have a .coding-os/ — we must NOT find them.
        for noisy in ("node_modules", ".venv", "__pycache__", ".git", "dist"):
            _make_project(root / noisy, "fake")
        with _client() as client:
            resp = client.post(
                "/api/hub/registry/scan",
                json={"root": str(root), "max_depth": 4, "limit": 20},
            )
        paths = [h["path"] for h in resp.json()["data"]["hits"]]
        # Only the legitimate "real" hit — no fakes under noise dirs.
        for p in paths:
            for noisy in ("node_modules", ".venv", "__pycache__", ".git", "dist"):
                assert f"/{noisy}/" not in p + "/", f"scan descended into {noisy}: {p}"

    def test_scan_rejects_missing_root(self, hub_env):
        with _client() as client:
            resp = client.post(
                "/api/hub/registry/scan",
                json={"root": str(hub_env["tmp"] / "nope")},
            )
        assert resp.status_code == 404

    def test_scan_honours_hit_limit(self, hub_env):
        root = hub_env["tmp"] / "many"
        root.mkdir()
        for i in range(5):
            _make_project(root, f"p{i}")
        with _client() as client:
            resp = client.post(
                "/api/hub/registry/scan",
                json={"root": str(root), "max_depth": 2, "limit": 3},
            )
        body = resp.json()["data"]
        assert body["count"] == 3
        assert body["hit_limit_reached"] is True


# ---------------------------------------------------------------------------
# POST /api/hub/registry/gc
# ---------------------------------------------------------------------------


class TestRegistryGc:
    def test_gc_prunes_dead_paths(self, hub_env):
        alive = _make_project(hub_env["tmp"], "alive")
        dead = _make_project(hub_env["tmp"], "will-die")
        with _client() as client:
            client.post("/api/hub/registry/add", json={"path": str(alive)})
            client.post("/api/hub/registry/add", json={"path": str(dead)})
        shutil.rmtree(dead)

        with _client() as client:
            resp = client.post("/api/hub/registry/gc", json={"dry_run": False})
        body = resp.json()["data"]
        kept_slugs = {e["slug"] for e in body["kept"]}
        removed_slugs = {e["slug"] for e in body["removed"]}
        assert "alive" in kept_slugs
        assert "will-die" in removed_slugs

        # Registry file now reflects the prune.
        import json

        reg_data = json.loads(hub_env["registry"].read_text())
        slugs_on_disk = {p["slug"] for p in reg_data["projects"]}
        assert "will-die" not in slugs_on_disk

    def test_gc_dry_run_does_not_mutate_file(self, hub_env):
        dead = _make_project(hub_env["tmp"], "dead")
        with _client() as client:
            client.post("/api/hub/registry/add", json={"path": str(dead)})
        shutil.rmtree(dead)

        before = hub_env["registry"].read_text()
        with _client() as client:
            resp = client.post("/api/hub/registry/gc", json={"dry_run": True})
        after = hub_env["registry"].read_text()
        assert before == after
        body = resp.json()["data"]
        assert body["dry_run"] is True
        assert {e["slug"] for e in body["removed"]} == {"dead"}


# ---------------------------------------------------------------------------
# GET /api/hub/suggest-roots
# ---------------------------------------------------------------------------


class TestSuggestRoots:
    def test_suggests_existing_directories_only(self, hub_env, monkeypatch):
        # Redirect HOME so the suggestion logic points at a known place.
        fake_home = hub_env["tmp"] / "fake-home"
        fake_home.mkdir()
        (fake_home / "Projects").mkdir()
        monkeypatch.setenv("HOME", str(fake_home))
        with _client() as client:
            resp = client.get("/api/hub/suggest-roots")
        assert resp.status_code == 200
        paths = resp.json()["data"]["suggestions"]
        assert str(fake_home / "Projects") in paths
        # ~/code wasn't created → must not appear.
        assert str(fake_home / "code") not in paths
