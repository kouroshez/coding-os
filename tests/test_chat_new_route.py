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


def _session_event_ids(body: str) -> list[str]:
    import json

    ids: list[str] = []
    for chunk in body.split("\n\n"):
        lines = chunk.splitlines()
        if not lines or lines[0].strip() != "event: session":
            continue
        for ln in lines[1:]:
            if ln.startswith("data:"):
                data = json.loads(ln[len("data:") :].strip())
                if "session_id" in data:
                    ids.append(data["session_id"])
    return ids


def test_chat_new_session_event_uses_sdk_resolved_id(client, monkeypatch):
    """The `session` event must carry the SDK's real transcript id, not the
    minted ses-claude-ui-* one — the SDK rekeys it, so the minted id would
    404 on get_chat and never list. (Hub chat-landing keystone.)"""
    import dataclasses

    @dataclasses.dataclass
    class FakeInit:
        session_id: str
        subtype: str = "init"

    class FakeSDK:
        def ClaudeAgentOptions(self, **kwargs):  # noqa: N802 — mirrors SDK name
            return kwargs

        async def query(self, prompt, options):
            yield FakeInit("real-sdk-uuid-9999")

    fake = FakeSDK()
    patched = False
    for modname in ("web.routes.cognition", "core.web.routes.cognition"):
        mod = sys.modules.get(modname)
        if mod is not None:
            monkeypatch.setattr(mod, "_claude_sdk", lambda: fake, raising=False)
            patched = True
    assert patched

    with client.stream("POST", "/api/cognition/chat", json={"prompt": "hi"}) as r:
        body = "".join(r.iter_text())

    session_ids = _session_event_ids(body)
    assert session_ids == ["real-sdk-uuid-9999"], session_ids
    assert not any(sid.startswith("ses-claude-ui-") for sid in session_ids)
