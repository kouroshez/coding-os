"""Live SDK contract test for the Hub chat stream (sdk_e2e / nightly only).

The FakeSDK guards in test_chat_new_route.py verify OUR logic against a hand-built
shape — they stay green even if the real claude-agent-sdk changes its StreamEvent
/ AssistantMessage shape. This test exercises the REAL SDK end to end and asserts
the shape contract the SPA depends on, so a silent upstream drift is caught:

  - streamevent frames carry ``event.delta.text``  (streamDeltaText / token-by-token)
  - assistant frames carry top-level ``model`` + ``usage``  (NewChatForm header)
  - the `session` id equals the `done` id and is a real UUID (never the minted one)
  - the session is queryable right after `done` (the "never vanish" contract)

Run:  COS_LIVE_TESTS=1 uv run pytest -m sdk_e2e tests/test_chat_live_contract.py
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_REPO_ROOT = Path(__file__).resolve().parent.parent
for _p in (_REPO_ROOT, _REPO_ROOT / "src" / "core"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

pytestmark = [
    pytest.mark.sdk_e2e,
    pytest.mark.skipif(
        os.environ.get("COS_LIVE_TESTS") != "1"
        or shutil.which("claude") is None
        or importlib.util.find_spec("claude_agent_sdk") is None,
        reason="live SDK contract — set COS_LIVE_TESTS=1 with an authed `claude` CLI on PATH",
    ),
]


def _frames(body: str) -> list[tuple[str, dict]]:
    out: list[tuple[str, dict]] = []
    for chunk in body.split("\n\n"):
        name = ""
        data = ""
        for ln in chunk.splitlines():
            if ln.startswith("event:"):
                name = ln[len("event:") :].strip()
            elif ln.startswith("data:"):
                data += ln[len("data:") :].strip()
        if not name:
            continue
        try:
            payload = json.loads(data) if data else {}
        except json.JSONDecodeError:
            payload = {}
        out.append((name, payload))
    return out


def _is_text_delta(payload: dict) -> bool:
    event = payload.get("event")
    if not isinstance(event, dict) or event.get("type") != "content_block_delta":
        return False
    delta = event.get("delta")
    return isinstance(delta, dict) and delta.get("type") == "text_delta"


@pytest.mark.timeout(150)
def test_live_chat_stream_shape_contract():
    from core.web.server import create_app

    with TestClient(create_app()) as c:
        with c.stream(
            "POST",
            "/api/cognition/chat",
            json={"prompt": "Reply with exactly one word: PONG", "model": "claude-haiku-4-5"},
        ) as r:
            body = "".join(r.iter_text())

        frames = _frames(body)

        # 1. Partial streaming: at least one streamevent carries a text_delta —
        #    the exact path streamDeltaText reads. Without it the UI stops
        #    painting token-by-token.
        text_deltas = [p for (n, p) in frames if n == "streamevent" and _is_text_delta(p)]
        assert text_deltas, "no streamevent text_delta frames — streamDeltaText contract broke"

        # 2. session id == done id, and a real SDK uuid (not the minted fallback
        #    that 404s — the "session vanished" cause).
        session_ids = [p["session_id"] for (n, p) in frames if n == "session" and "session_id" in p]
        done_ids = [p["session_id"] for (n, p) in frames if n == "done" and "session_id" in p]
        assert session_ids and done_ids, (session_ids, done_ids)
        sid = done_ids[-1]
        assert session_ids[-1] == sid, (session_ids, done_ids)
        assert not sid.startswith("ses-claude-ui-"), f"SDK never resolved a real session id: {sid}"

        # 3. assistant frames carry top-level model + usage (NewChatForm reads
        #    these for the "assistant · model · tok" header).
        assistants = [p for (n, p) in frames if n == "assistant"]
        assert assistants, "no assistant frame in the stream"
        assert any(a.get("model") for a in assistants), "assistant frame missing top-level model"
        assert any(isinstance(a.get("usage"), dict) for a in assistants), "assistant frame missing usage"

        # 4. The session is queryable right after done — mirror the frontend's
        #    grace window (the jsonl flush can lag by a beat).
        ok = False
        for _ in range(10):
            if c.get(f"/api/cognition/chat/{sid}").status_code == 200:
                ok = True
                break
            time.sleep(1)
        assert ok, f"get_chat 404'd on a just-created session {sid} after 10s"
