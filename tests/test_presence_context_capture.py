"""TASK-255 — presence token-capture so live-agent context % is real.

Covers presence_write.py (stamps used_tokens on stop from the live transcript)
and presence.py (derives context_pct from the stamped used_tokens, honest-null
when absent).
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_REPO_ROOT = Path(__file__).resolve().parent.parent
for _p in (_REPO_ROOT, _REPO_ROOT / "src" / "core"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from core.web.server import create_app  # noqa: E402

_HELPER = _REPO_ROOT / "src" / "core" / "hooks" / "_helpers" / "presence_write.py"
_spec = importlib.util.spec_from_file_location("presence_write", _HELPER)
presence_write = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(presence_write)


def _transcript(tmp_path: Path, usage: dict | None) -> Path:
    p = tmp_path / "transcript.jsonl"
    lines = ['{"type":"user","message":{"role":"user","content":"hi"}}']
    if usage is not None:
        lines.append(json.dumps({"type": "assistant", "message": {"usage": usage}}))
    p.write_text("\n".join(lines) + "\n")
    return p


def _run(session_json: Path, event: str, transcript: str = "", *, now: int = 1000) -> dict:
    presence_write.main(
        [
            "presence_write.py",
            str(session_json),
            "claude",
            "ses-x",
            str(os.getpid()),
            event,
            str(now),
            "claude-opus-4-8[1m]",
            "SDK-1",
            transcript,
        ]
    )
    return json.loads(session_json.read_text())


class TestPresenceWriteCapture:
    def test_stop_stamps_used_tokens(self, tmp_path):
        tr = _transcript(
            tmp_path,
            {"input_tokens": 100_000, "cache_read_input_tokens": 50_000},
        )
        out = _run(tmp_path / "s.json", "stop", str(tr), now=4242)
        assert out["used_tokens"] == 150_000
        assert out["context_updated_at"] == 4242

    def test_stop_without_usage_fails_open(self, tmp_path):
        tr = _transcript(tmp_path, None)
        out = _run(tmp_path / "s.json", "stop", str(tr))
        assert out["used_tokens"] is None

    def test_non_stop_event_does_not_read_transcript(self, tmp_path):
        # seed a prior used_tokens, then a tool event must preserve it untouched
        session = tmp_path / "s.json"
        session.write_text(json.dumps({"used_tokens": 999, "started_at": 1}))
        tr = _transcript(tmp_path, {"input_tokens": 12345})
        out = _run(session, "tool", str(tr))
        assert out["used_tokens"] == 999  # tool event never tails the transcript

    def test_missing_transcript_path_is_safe(self, tmp_path):
        out = _run(tmp_path / "s.json", "stop", "")
        assert out["used_tokens"] is None


class TestContextPctFromUsedTokens:
    def test_pct_1m_window(self):
        from core.web.routes.presence import _context_pct_from_used_tokens

        assert _context_pct_from_used_tokens(500_000, "claude-opus-4-8[1m]") == 50.0

    def test_pct_standard_window(self):
        from core.web.routes.presence import _context_pct_from_used_tokens

        assert _context_pct_from_used_tokens(100_000, "claude-opus-4-8") == 50.0

    def test_pct_none_and_caps(self):
        from core.web.routes.presence import _context_pct_from_used_tokens

        assert _context_pct_from_used_tokens(None, "x") is None
        assert _context_pct_from_used_tokens(0, "x") is None
        assert _context_pct_from_used_tokens(10**9, "x") == 100.0


class TestPresenceAgentsUsesStampedTokens:
    @pytest.fixture
    def client(self, tmp_path, monkeypatch):
        state = tmp_path / ".coding-os"
        sessions = state / "claude" / "sessions"
        sessions.mkdir(parents=True)
        sid = "ses-claude-ctx"
        (state / "claude" / "session-id").write_text(sid)
        (sessions / f"{sid}.json").write_text(
            json.dumps(
                {
                    "agent": "claude",
                    "session_id": sid,
                    "model": "claude-opus-4-8[1m]",
                    "used_tokens": 250_000,
                    "last_tool_at": 9_999_999_999,
                    "pid": os.getpid(),
                }
            )
        )
        monkeypatch.setenv("COS_STATE_DIR", str(state))
        monkeypatch.setenv("COS_PROJECT_ROOT", str(tmp_path))
        with TestClient(create_app()) as c:
            yield c

    def test_context_pct_derived_from_stamped_tokens(self, client):
        r = client.get("/api/presence/agents")
        assert r.status_code == 200
        claude = next(a for a in r.json()["data"]["agents"] if a["agent"] == "claude")
        assert claude["context_pct"] == 25.0  # 250k / 1M
        assert claude["used_tokens"] == 250_000
        assert claude["context_window"] == 1_000_000
