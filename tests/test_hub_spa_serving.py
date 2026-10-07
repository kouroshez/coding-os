"""The hub decides per request whether the SPA is built, so a build never needs a restart."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "core"))

from web import server

DEEP_LINK = "/p/coding-os/board"


@pytest.fixture
def dist(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    spa_dist = tmp_path / "dist"
    monkeypatch.setattr(server, "_SPA_DIST", spa_dist)
    return spa_dist


@pytest.fixture
def client(dist: Path) -> TestClient:
    return TestClient(server.create_app())


def _build(dist: Path) -> None:
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>spa</html>")
    (dist / "assets" / "index-abc123.js").write_text("console.log(1)")
    (dist / "favicon.png").write_bytes(b"png")


def test_missing_dist_answers_every_spa_route_with_build_instructions(client: TestClient) -> None:
    for path in ("/", DEEP_LINK, "/assets/index-abc123.js"):
        response = client.get(path)
        assert response.status_code == 503, path
        assert "make ui-build" in response.text


def test_unknown_api_path_stays_a_json_404(client: TestClient) -> None:
    response = client.get("/api/does-not-exist")
    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}


def test_a_build_after_startup_is_served_without_restart(client: TestClient, dist: Path) -> None:
    assert client.get(DEEP_LINK).status_code == 503
    _build(dist)
    response = client.get(DEEP_LINK)
    assert response.status_code == 200
    assert response.text == "<html>spa</html>"
    assert response.headers["cache-control"] == "no-cache, must-revalidate"


def test_built_files_are_served_and_traversal_is_refused(client: TestClient, dist: Path) -> None:
    _build(dist)
    (dist.parent / "secret.txt").write_text("outside dist")
    assert client.get("/assets/index-abc123.js").text == "console.log(1)"
    assert client.get("/favicon.png").content == b"png"
    assert client.get("/%2e%2e/secret.txt").status_code == 404
