from __future__ import annotations

from pathlib import Path

import tracing


def test_emit_defaults_to_agent_scoped_dir(monkeypatch, tmp_path):
    state = tmp_path / ".coding-os"
    monkeypatch.setenv("COS_STATE_DIR", str(state))
    monkeypatch.setenv("COS_AGENT", "codex")

    tracing.emit("ses-unit-1", "analyze_start", {"x": 1})

    target = state / "codex" / "traces" / "ses-unit-1.jsonl"
    assert target.exists()
    body = target.read_text(encoding="utf-8")
    assert '"kind":"analyze_start"' in body


def test_emit_prefers_cos_agent_dir(monkeypatch, tmp_path):
    agent_dir = tmp_path / "agent-root"
    monkeypatch.setenv("COS_AGENT_DIR", str(agent_dir))
    monkeypatch.delenv("COS_STATE_DIR", raising=False)

    tracing.emit("ses-unit-2", "compose_done", {"chain": ["F1"]})

    target = agent_dir / "traces" / "ses-unit-2.jsonl"
    assert target.exists()
