"""Guards for the read-only Configuration routes (/api/config/*).

Available stacks/skills come from the installed package registry (deterministic
regardless of cwd); installed/mcp come from the active project files.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_REPO_ROOT = Path(__file__).resolve().parent.parent
for _p in (_REPO_ROOT, _REPO_ROOT / "src", _REPO_ROOT / "src" / "core"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from core.web.server import create_app


@pytest.fixture
def client():
    with TestClient(create_app()) as c:
        yield c


def test_stacks_lists_available_registry(client):
    r = client.get("/api/config/stacks")
    assert r.status_code == 200
    body = r.json()
    assert "available" in body and "installed" in body
    ids = {s["id"] for s in body["available"]}
    assert "meta" in ids  # the package always ships the meta stack
    for s in body["available"]:
        assert {"id", "label", "category", "primary_skill", "installed"} <= set(s)


def test_skills_lists_core_registry(client):
    r = client.get("/api/config/skills")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] > 0
    names = {s["name"] for s in body["skills"]}
    assert "clean-code" in names  # a core skill that always exists
    for s in body["skills"]:
        assert {"name", "tier", "domain"} <= set(s)


def test_mcp_reports_servers_shape(client):
    r = client.get("/api/config/mcp")
    assert r.status_code == 200
    body = r.json()
    assert "servers" in body
    for s in body["servers"]:
        assert "name" in s and "command" in s and "managed" in s
