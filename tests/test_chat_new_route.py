"""Guards for the fresh-session runner POST /api/cognition/chat (TASK-186).

The streaming path needs a live Claude SDK + a real session, so these cover the
deterministic guards (validation, unavailable) and the role-prompt resolver.
"""

from __future__ import annotations

import dataclasses
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


# ---------------------------------------------------------------------------
# Guardians for the "session vanished" + token-by-token streaming contracts.
# These fail the instant a regression breaks the chat lifecycle (TASK chat-hardening).
# ---------------------------------------------------------------------------


def _event_ids(body: str, event_name: str) -> list[str]:
    import json

    ids: list[str] = []
    for chunk in body.split("\n\n"):
        lines = chunk.splitlines()
        if not lines or lines[0].strip() != f"event: {event_name}":
            continue
        for ln in lines[1:]:
            if ln.startswith("data:"):
                data = json.loads(ln[len("data:") :].strip())
                if "session_id" in data:
                    ids.append(data["session_id"])
    return ids


def _make_fake_sdk(events, captured_opts=None):
    class FakeSDK:
        def ClaudeAgentOptions(self, **kwargs):  # noqa: N802 — mirrors SDK name
            if captured_opts is not None:
                captured_opts.update(kwargs)
            return kwargs

        async def query(self, prompt, options):
            if captured_opts is not None:
                captured_opts["_options"] = options
            for ev in events:
                yield ev

    return FakeSDK()


def _patch_sdk(monkeypatch, fake):
    patched = False
    for modname in ("web.routes.cognition", "core.web.routes.cognition"):
        mod = sys.modules.get(modname)
        if mod is not None:
            monkeypatch.setattr(mod, "_claude_sdk", lambda: fake, raising=False)
            patched = True
    assert patched, "cognition module not loaded"


@dataclasses.dataclass
class _Init:
    session_id: str
    subtype: str = "init"


@dataclasses.dataclass
class _NoId:
    subtype: str = "noise"


def test_chat_new_session_and_done_ids_match(client, monkeypatch):
    """Invariant: the `session` event id equals the `done` event id. A mismatch
    strands the UI on an id that 404s on get_chat — the 'session vanished' bug."""
    _patch_sdk(monkeypatch, _make_fake_sdk([_Init("real-uuid-1")]))
    with client.stream("POST", "/api/cognition/chat", json={"prompt": "hi"}) as r:
        body = "".join(r.iter_text())
    session_ids = _event_ids(body, "session")
    done_ids = _event_ids(body, "done")
    assert session_ids and done_ids, (session_ids, done_ids)
    assert session_ids[-1] == done_ids[-1] == "real-uuid-1"


def test_chat_new_no_session_id_warns_and_falls_back(client, monkeypatch):
    """When the SDK never yields a session_id the UI is handed the minted id
    (which 404s). That MUST be logged at warning — never silent."""
    warned: list[str] = []
    for modname in ("web.routes.cognition", "core.web.routes.cognition"):
        mod = sys.modules.get(modname)
        if mod is not None:
            monkeypatch.setattr(
                mod.logger, "warning", lambda *a, **k: warned.append(a[0] if a else "")
            )
    _patch_sdk(monkeypatch, _make_fake_sdk([_NoId()]))
    with client.stream("POST", "/api/cognition/chat", json={"prompt": "hi"}) as r:
        body = "".join(r.iter_text())
    done_ids = _event_ids(body, "done")
    assert done_ids and done_ids[0].startswith("ses-claude-ui-"), done_ids
    assert any("no SDK session_id" in str(m) for m in warned), warned


def test_chat_new_enables_partial_streaming(client, monkeypatch):
    """include_partial_messages must stay True — without it the SDK yields one
    complete message and the reply stops streaming token-by-token."""
    captured: dict = {}
    _patch_sdk(monkeypatch, _make_fake_sdk([_Init("uuid-2")], captured_opts=captured))
    with client.stream("POST", "/api/cognition/chat", json={"prompt": "hi"}) as r:
        "".join(r.iter_text())
    # Options are now built by the SSOT builder (TASK-417); assert via the
    # ClaudeAgentOptions object the route hands to query().
    opts = captured.get("_options")
    assert getattr(opts, "include_partial_messages", None) is True
    # routed through the SSOT builder: chat profile registers cos_*, no Write
    assert "mcp__coding-os__*" in getattr(opts, "allowed_tools", [])
    assert "Write" not in getattr(opts, "allowed_tools", [])


def test_get_chat_missing_session_returns_404(client, monkeypatch):
    """A missing session is a 404 (not a 500) so the UI can distinguish a flush
    race (retry quietly) from a hard error."""

    class FakeSDK:
        def get_session_info(self, session_id, directory):
            return None

    _patch_sdk(monkeypatch, FakeSDK())
    r = client.get("/api/cognition/chat/does-not-exist")
    assert r.status_code == 404


def test_chat_send_streams_partial_and_skips_project_hooks(client, monkeypatch):
    """Follow-up turns must ALSO stream token-by-token (include_partial_messages)
    and skip the project hook suite (setting_sources=[]) — a silent regression
    here makes resumed replies dump all at once / re-run the banner+governance."""
    captured: dict = {}
    _patch_sdk(monkeypatch, _make_fake_sdk([_Init("uuid-3")], captured_opts=captured))
    with client.stream(
        "POST", "/api/cognition/chat/some-session-id/send", json={"prompt": "more"}
    ) as r:
        "".join(r.iter_text())
    opts = captured.get("_options")
    assert getattr(opts, "include_partial_messages", None) is True
    assert getattr(opts, "setting_sources", None) == []
    assert "mcp__coding-os__*" in getattr(opts, "allowed_tools", [])


# ---------------------------------------------------------------------------
# Auto model routing (TASK-318 — hub-architecture.md § Hub settings contract)
# ---------------------------------------------------------------------------


def _cognition_mod():
    for modname in ("web.routes.cognition", "core.web.routes.cognition"):
        mod = sys.modules.get(modname)
        if mod is not None:
            return mod
    raise AssertionError("cognition route module not loaded")


def _enable_routing(client, orchestrator=""):
    body = {"model_routing": {"enabled": True, "orchestrator_model": orchestrator}}
    assert client.patch("/api/settings", json=body).status_code == 200


def test_auto_rejected_when_routing_disabled(client):
    r = client.post("/api/cognition/chat", json={"prompt": "hello", "model": "auto"})
    assert r.json()["error"]["category"] == "validation"
    assert "model_routing.enabled" in r.json()["error"]["message"]


def test_auto_cold_start_uses_orchestrator_model(client, monkeypatch):
    _enable_routing(client, orchestrator="claude-haiku-4-5")
    mod = _cognition_mod()

    import tools.routing as routing_mod

    monkeypatch.setattr(
        routing_mod,
        "route_model",
        lambda conn, **kw: {"recommended_model": "static-cold", "data_points": 0},
    )
    decision = mod._auto_route_model("design a backend api integration")
    assert decision["model"] == "claude-haiku-4-5"
    assert decision["source"] == "orchestrator_default"
    assert decision["complexity"] == "COMPLICATED"


def test_auto_prefers_empirical_when_history_exists(client, monkeypatch):
    _enable_routing(client, orchestrator="claude-haiku-4-5")
    mod = _cognition_mod()

    import tools.routing as routing_mod

    monkeypatch.setattr(
        routing_mod,
        "route_model",
        lambda conn, **kw: {"recommended_model": "claude-opus-4-8", "data_points": 25},
    )
    decision = mod._auto_route_model("fix the broken outage now")
    assert decision["model"] == "claude-opus-4-8"
    assert decision["source"] == "empirical"
    assert decision["complexity"] == "CHAOTIC"
