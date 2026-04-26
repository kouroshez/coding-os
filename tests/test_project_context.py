"""Tests for core.web._project_context — middleware + contextvar scope."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.web._project_context import (
    ProjectScopeMiddleware,
    current_db_path,
    current_project_root,
)


def _mk_project(root: Path, slug: str) -> Path:
    project = root / slug
    (project / ".coding-os").mkdir(parents=True)
    return project.resolve()


@pytest.fixture
def hub_app(tmp_path, monkeypatch):
    """Build a tiny FastAPI app with the middleware + two probe routes."""
    registry_file = tmp_path / "registry.json"
    monkeypatch.setenv("COS_REGISTRY_PATH", str(registry_file))

    project_alpha = _mk_project(tmp_path, "alpha")
    project_beta = _mk_project(tmp_path, "beta")

    registry_file.write_text(
        json.dumps(
            {
                "version": 1,
                "projects": [
                    {"slug": "alpha", "path": str(project_alpha), "created_at": ""},
                    {"slug": "beta", "path": str(project_beta), "created_at": ""},
                ],
            }
        ),
        encoding="utf-8",
    )

    app = FastAPI()
    app.add_middleware(ProjectScopeMiddleware)

    @app.get("/api/whoami")
    def whoami() -> dict:
        return {
            "project_root": str(current_project_root()),
            "db_path": str(current_db_path()),
        }

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    return app, {"alpha": project_alpha, "beta": project_beta}


def test_no_prefix_falls_back_to_env(hub_app, monkeypatch, tmp_path):
    app, _ = hub_app
    monkeypatch.setenv("COS_PROJECT_ROOT", str(tmp_path))
    client = TestClient(app)
    resp = client.get("/api/whoami")
    assert resp.status_code == 200
    body = resp.json()
    assert body["project_root"] == str(tmp_path.resolve())


def test_scoped_prefix_picks_alpha(hub_app):
    app, projects = hub_app
    client = TestClient(app)
    resp = client.get("/api/p/alpha/whoami")
    assert resp.status_code == 200
    body = resp.json()
    assert body["project_root"] == str(projects["alpha"])
    assert body["db_path"].endswith(
        f"{projects['alpha'].name}/.coding-os/thinking_os.db"
    )


def test_scoped_prefix_picks_beta(hub_app):
    app, projects = hub_app
    client = TestClient(app)
    resp = client.get("/api/p/beta/whoami")
    assert resp.status_code == 200
    assert resp.json()["project_root"] == str(projects["beta"])


def test_unknown_slug_is_404(hub_app):
    app, _ = hub_app
    client = TestClient(app)
    resp = client.get("/api/p/ghost/whoami")
    assert resp.status_code == 404
    assert "not in registry" in resp.json()["detail"]


def test_non_api_path_passes_through(hub_app):
    app, _ = hub_app
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_contextvar_is_reset_after_request(hub_app, tmp_path):
    app, projects = hub_app
    client = TestClient(app)
    # First request scopes to alpha.
    client.get("/api/p/alpha/whoami")
    # After it returns the ContextVar must be reset — next unscoped
    # request must not leak alpha.
    resp = client.get("/api/whoami")
    # Without env, fallback is cwd (the repo root during tests).  The
    # important invariant is: the resolved path is NOT projects["alpha"].
    assert resp.json()["project_root"] != str(projects["alpha"])
