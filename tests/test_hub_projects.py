"""Tests for /api/hub/projects filtering + auto cwd entry."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from web.server import create_app  # noqa: E402


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
    matching = [
        p
        for p in data["projects"]
        if Path(p["path"]).resolve() == hub_fixture["cwd_project"].resolve()
    ]
    assert len(matching) == 1


def test_nested_coding_os_is_not_a_project(hub_fixture, monkeypatch):
    """A stray .coding-os/ inside a registered project must NEVER appear.

    Regression for the bug where src/core/web/ui/.coding-os/ surfaced as
    a project named "ui" and stole the Hub's default slot.
    """
    from cli.registry import add_project

    add_project(hub_fixture["cwd_project"])
    nested = hub_fixture["cwd_project"] / "src" / "core" / "web" / "ui"
    (nested / ".coding-os").mkdir(parents=True)
    monkeypatch.chdir(nested)
    monkeypatch.setenv("COS_PROJECT_ROOT", str(nested))

    with _client() as client:
        resp = client.get("/api/hub/projects")
    data = resp.json()
    paths = {Path(p["path"]).resolve() for p in data["projects"]}
    assert nested.resolve() not in paths
    assert hub_fixture["cwd_project"].resolve() in paths


def test_registry_add_rejects_nested_coding_os(hub_fixture):
    """POST /api/hub/registry/add must refuse paths inside another project."""
    from cli.registry import add_project

    add_project(hub_fixture["cwd_project"])
    nested = hub_fixture["cwd_project"] / "vendor" / "thing"
    (nested / ".coding-os").mkdir(parents=True)

    with _client() as client:
        resp = client.post(
            "/api/hub/registry/add",
            json={"path": str(nested)},
        )
    assert resp.status_code == 400
    body = resp.json()
    assert "inside" in body["error"]["message"].lower()


def test_unregistered_ancestor_coding_os_does_not_block(hub_fixture):
    """Issue reported 2026-05-23: contributor cloned coding-os to
    `~/p/coding-os/` while a stray `~/.coding-os/` (test artefact)
    existed in their home dir. The nested-project check rejected the
    legitimate checkout. Fix: only enforce nesting when the ancestor
    is REGISTERED in the cli registry — stray `.coding-os/` is noise.
    """
    from cli.registry import add_project

    # Create the ancestor `.coding-os/` but do NOT register it.
    parent = hub_fixture["tmp"] / "noisy-parent"
    parent.mkdir()
    (parent / ".coding-os").mkdir()
    # The legit project sits under the noisy parent.
    inner = parent / "legit-project"
    (inner / ".coding-os").mkdir(parents=True)

    with _client() as client:
        resp = client.post(
            "/api/hub/registry/add",
            json={"path": str(inner)},
        )
    assert resp.status_code == 200, resp.json()

    # And re-registering the ancestor must now flip the check back to reject.
    add_project(parent)
    inner2 = parent / "another-legit"
    (inner2 / ".coding-os").mkdir(parents=True)
    with _client() as client:
        resp2 = client.post(
            "/api/hub/registry/add",
            json={"path": str(inner2)},
        )
    assert resp2.status_code == 400
    assert "inside" in resp2.json()["error"]["message"].lower()


def test_meta_repo_is_never_flagged_nested(hub_fixture):
    """Dogfood: the meta-repo's own checkout has `.coding-os/` (P5
    Dogfood). Even if the user has a `.coding-os/` higher in the
    tree, the meta-repo checkout must register fine.
    """
    parent = hub_fixture["tmp"] / "home-noise"
    parent.mkdir()
    (parent / ".coding-os").mkdir()
    meta = parent / "coding-os"
    (meta / ".coding-os").mkdir(parents=True)
    # Lay down the meta-repo signature files so _is_meta_repo() returns True.
    (meta / "pyproject.toml").write_text("[project]\nname = 'coding-os'\n")
    (meta / "src" / "cli").mkdir(parents=True)
    (meta / "src" / "cli" / "main.py").write_text("# meta cli\n")
    (meta / "src" / "core" / "thinking_os").mkdir(parents=True)
    (meta / "src" / "core" / "thinking_os" / "server.py").write_text("# mcp server\n")

    with _client() as client:
        resp = client.post(
            "/api/hub/registry/add",
            json={"path": str(meta)},
        )
    assert resp.status_code == 200, resp.json()
