"""Settings + gating contract for board drag auto-spawn:
default-off, PATCH round-trip, and _auto_spawn_safe fires only for a human
icebox→in_progress move with the toggle on.
Spec: docs/engineering/hub-architecture.md § Hub settings contract.
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

from core.web.routes import board as board_routes
from core.web.server import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("COS_STATE_DIR", str(tmp_path))
    return TestClient(create_app())


def test_auto_spawn_defaults_off(client):
    payload = client.get("/api/settings").json()["data"]
    assert payload["settings"]["auto_spawn"] == {"enabled": False}


def test_auto_spawn_patch_round_trips(client):
    patched = client.patch("/api/settings", json={"auto_spawn": {"enabled": True}}).json()["data"]
    assert patched["settings"]["auto_spawn"]["enabled"] is True
    fetched = client.get("/api/settings").json()["data"]
    assert fetched["settings"]["auto_spawn"]["enabled"] is True


@pytest.fixture
def spawn_capture(monkeypatch, tmp_path):
    calls: list[str] = []
    monkeypatch.setattr(
        board_routes,
        "_auto_spawn_run",
        lambda task_id, root, db: calls.append(task_id),
    )
    from web import _project_context

    monkeypatch.setattr(_project_context, "current_project_root", lambda: tmp_path)
    monkeypatch.setattr(_project_context, "current_db_path", lambda: tmp_path / "db.sqlite")
    return calls


def _wait_threads():
    import threading

    for t in threading.enumerate():
        if t is not threading.current_thread() and t.daemon and t.is_alive():
            t.join(timeout=2)


def test_gate_fires_only_for_human_icebox_pull(monkeypatch, spawn_capture):
    monkeypatch.setattr(board_routes, "_auto_spawn_enabled", lambda: True)

    board_routes._auto_spawn_safe("TASK-1", "icebox", "in_progress", None)
    _wait_threads()
    assert spawn_capture == ["TASK-1"]

    board_routes._auto_spawn_safe("TASK-2", "icebox", "in_progress", "human")
    _wait_threads()
    assert "TASK-2" in spawn_capture


def test_gate_skips_agent_moves_and_other_transitions(monkeypatch, spawn_capture):
    monkeypatch.setattr(board_routes, "_auto_spawn_enabled", lambda: True)

    board_routes._auto_spawn_safe("TASK-3", "icebox", "in_progress", "ses-claude-123")
    board_routes._auto_spawn_safe("TASK-4", "in_progress", "testing", None)
    board_routes._auto_spawn_safe("TASK-5", "blocked", "in_progress", None)
    _wait_threads()
    assert spawn_capture == []


def test_gate_skips_when_toggle_off(monkeypatch, spawn_capture):
    monkeypatch.setattr(board_routes, "_auto_spawn_enabled", lambda: False)
    board_routes._auto_spawn_safe("TASK-6", "icebox", "in_progress", None)
    _wait_threads()
    assert spawn_capture == []


def test_gate_dedups_inflight_spawns(monkeypatch, spawn_capture):
    monkeypatch.setattr(board_routes, "_auto_spawn_enabled", lambda: True)
    with board_routes._auto_spawn_lock:
        board_routes._auto_spawn_inflight.add("TASK-7")
    try:
        board_routes._auto_spawn_safe("TASK-7", "icebox", "in_progress", None)
        _wait_threads()
        assert spawn_capture == []
    finally:
        with board_routes._auto_spawn_lock:
            board_routes._auto_spawn_inflight.discard("TASK-7")
