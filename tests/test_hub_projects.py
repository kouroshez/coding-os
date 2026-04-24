"""Tests for /api/hub/projects filtering + auto cwd entry.

PURPOSE: Guard the Hub landing page so it:
  1. Hides registry entries whose directory no longer exists (pytest
     tmp dirs that leaked into ~/.coding-os/registry.json).
  2. Surfaces the currently-running project (cwd) even when it was
     never explicitly registered, so the meta-project you are serving
     from always shows up.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from core.web.server import create_app  # noqa: E402


@pytest.fixture
def hub_fixture(tmp_path, monkeypatch):
    """Give each test an isolated registry + a cwd-style project."""
    registry = tmp_path / "registry.json"
    monkeypatch.setenv("COS_REGISTRY_PATH", str(registry))

    cwd_project = tmp_path / "meta-project"
    (cwd_project / ".coding-os").mkdir(parents=True)
    monkeypatch.setenv("COS_PROJECT_ROOT", str(cwd_project))
    monkeypatch.chdir(cwd_project)

    return {
        "registry": registry,
        "cwd_project": cwd_project,
        "tmp": tmp_path,
    }


def _client() -> TestClient:
    return TestClient(create_app())


def test_cwd_project_auto_listed_when_registry_empty(hub_fixture):
    """Even without a `cos init`, the running project appears in the list."""
    with _client() as client:
        resp = client.get("/api/hub/projects")
    assert resp.status_code == 200
    data = resp.json()
    slugs = [p["slug"] for p in data["projects"]]
    assert "meta-project" in slugs
    assert data["count"] >= 1


def test_stale_path_is_filtered(hub_fixture):
    """Registry entries whose directory was deleted must not reach the UI."""
    from cli.registry import add_project

    alive = hub_fixture["tmp"] / "alive"
    (alive / ".coding-os").mkdir(parents=True)
    dead = hub_fixture["tmp"] / "will-be-removed"
    (dead / ".coding-os").mkdir(parents=True)

    add_project(alive)
    add_project(dead)

    import shutil

    shutil.rmtree(dead)

    with _client() as client:
        resp = client.get("/api/hub/projects")
    data = resp.json()
    slugs = [p["slug"] for p in data["projects"]]
    assert "alive" in slugs
    assert "will-be-removed" not in slugs


def test_cwd_not_duplicated_when_already_registered(hub_fixture):
    """cwd entry must not double-list a project that's already in registry."""
    from cli.registry import add_project

    add_project(hub_fixture["cwd_project"])

    with _client() as client:
        resp = client.get("/api/hub/projects")
    data = resp.json()
    matching = [p for p in data["projects"]
                if Path(p["path"]).resolve() == hub_fixture["cwd_project"].resolve()]
    assert len(matching) == 1
