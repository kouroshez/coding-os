"""Tests for core.board_os.viewer.server — L.5 web viewer."""

from __future__ import annotations

import importlib.util
import json
import sqlite3
from pathlib import Path

import pytest
import yaml


aiohttp = pytest.importorskip("aiohttp")
from aiohttp.test_utils import TestClient, TestServer

from core.board_os.viewer.server import build_app
from core.board_os import mcp_tools


def _load_db_module():
    spec = importlib.util.spec_from_file_location(
        "_db_under_test",
        Path(__file__).resolve().parents[2] / "thinking-os" / "db.py",
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


db = _load_db_module()


@pytest.fixture
def project(tmp_path: Path, monkeypatch) -> Path:
    (tmp_path / ".coding-os").mkdir()
    (tmp_path / ".coding-os" / "scrumban-config.yaml").write_text(
        yaml.safe_dump({
            "swimlanes": [
                {"id": "core", "label": "Core", "color": "#3b82f6"},
            ],
            "wip_limits": {"in_progress": 5, "testing": 5, "emergency": 2},
        }),
        encoding="utf-8",
    )
    (tmp_path / "docs" / "tasks").mkdir(parents=True)
    monkeypatch.setenv("COS_PROJECT_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    p = str(tmp_path / "thinking-os.db")
    db.init_db(p).close()
    return p


@pytest.mark.asyncio
async def test_index_serves_html(project: Path, db_path: str):
    def factory():
        return sqlite3.connect(db_path)
    app = build_app(factory, project_root=project)
    async with TestClient(TestServer(app)) as c:
        async with c.get("/") as resp:
            assert resp.status == 200
            body = await resp.text()
            assert "cos-board" in body
            assert "Sortable" in body


@pytest.mark.asyncio
async def test_api_board_returns_envelope(project: Path, db_path: str):
    def factory():
        return sqlite3.connect(db_path)
    app = build_app(factory, project_root=project)
    async with TestClient(TestServer(app)) as c:
        async with c.get("/api/board") as resp:
            assert resp.status == 200
            env = json.loads(await resp.text())
            assert env["ok"] is True
            assert env["data"]["count"] == 0


@pytest.mark.asyncio
async def test_api_move_happy_path(project: Path, db_path: str):
    # Seed a task.
    conn = sqlite3.connect(db_path)
    try:
        mcp_tools.cos_task_create(
            conn, title="mover", swimlane="core", kind="feature",
        )
    finally:
        conn.close()

    def factory():
        return sqlite3.connect(db_path)
    app = build_app(factory, project_root=project)

    async with TestClient(TestServer(app)) as c:
        async with c.post(
            "/api/move",
            json={"task_id": "TASK-001", "to": "ready"},
        ) as resp:
            assert resp.status == 200
            env = json.loads(await resp.text())
            assert env["ok"] is True
            assert env["data"]["new_status"] == "ready"


@pytest.mark.asyncio
async def test_api_move_bad_json_returns_400(project: Path, db_path: str):
    def factory():
        return sqlite3.connect(db_path)
    app = build_app(factory, project_root=project)
    async with TestClient(TestServer(app)) as c:
        async with c.post("/api/move", data="not-json") as resp:
            assert resp.status == 400


@pytest.mark.asyncio
async def test_api_move_missing_fields_returns_400(project: Path, db_path: str):
    def factory():
        return sqlite3.connect(db_path)
    app = build_app(factory, project_root=project)
    async with TestClient(TestServer(app)) as c:
        async with c.post("/api/move", json={}) as resp:
            assert resp.status == 400


@pytest.mark.asyncio
async def test_auth_token_required_when_set(project: Path, db_path: str):
    def factory():
        return sqlite3.connect(db_path)
    app = build_app(factory, auth_token="secret-abc", project_root=project)
    async with TestClient(TestServer(app)) as c:
        # Without token.
        async with c.get("/api/board") as resp:
            assert resp.status == 401
        # With token.
        async with c.get("/api/board?token=secret-abc") as resp:
            assert resp.status == 200
