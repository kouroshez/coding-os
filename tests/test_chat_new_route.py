"""Guards for the fresh-session runner POST /api/cognition/chat (TASK-186).

The streaming path needs a live Claude SDK + a real session, so these cover the
deterministic guards (validation, unavailable) and the role-prompt resolver.
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

from core.web.server import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    state = tmp_path / ".coding-os"
    (state / "claude").mkdir(parents=True)
    monkeypatch.setenv("COS_STATE_DIR", str(state))
    with TestClient(create_app()) as c:
        yield c


def test_empty_prompt_rejected(client):
    r = client.post("/api/cognition/chat", json={"prompt": "  "})
    assert r.json()["error"]["category"] == "validation"


def test_unavailable_without_sdk(client, monkeypatch):
    # src/core on sys.path means the app may register the module as either
    # 'web.routes.cognition' or 'core.web.routes.cognition' — patch whichever
    # is loaded so we never spawn a real Claude process in the test.
    patched = False
    for modname in ("web.routes.cognition", "core.web.routes.cognition"):
        mod = sys.modules.get(modname)
        if mod is not None:
            monkeypatch.setattr(mod, "_claude_sdk", lambda: None, raising=False)
            patched = True
    assert patched, "cognition module not loaded"
    r = client.post("/api/cognition/chat", json={"prompt": "hello"})
    assert r.json()["error"]["category"] == "unavailable"


def test_role_system_prompt_resolution():
    from core.web.routes import cognition

    assert cognition._role_system_prompt("") is None
    assert cognition._role_system_prompt("../evil") is None
    sp = cognition._role_system_prompt("analyst")
    assert isinstance(sp, dict)
    assert sp["type"] == "preset"
    assert "append" in sp and sp["append"]


def test_author_task_empty_prompt_rejected(client):
    r = client.post("/api/cognition/author-task", json={"prompt": ""})
    assert r.json()["error"]["category"] == "validation"


def test_author_task_unavailable_without_sdk(client, monkeypatch):
    patched = False
    for modname in ("web.routes.cognition", "core.web.routes.cognition"):
        mod = sys.modules.get(modname)
        if mod is not None:
            monkeypatch.setattr(mod, "_claude_sdk", lambda: None, raising=False)
            patched = True
    assert patched
    r = client.post("/api/cognition/author-task", json={"prompt": "make a task for X"})
    assert r.json()["error"]["category"] == "unavailable"
