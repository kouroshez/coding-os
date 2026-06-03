"""TASK-063 — compose→trace wiring.

Regression guard for the bug where the auto-compose hook stamped .roles/.role
markers but never emitted a `compose_done` trace, so the Hub /api/roles panel
(which reads compose_done) was always empty. Both the shared emitter and the
end-to-end auto_compose path must drop a compose_done event into the
agent-level traces dir the panel scans.
"""

from __future__ import annotations

import sys
from pathlib import Path

import formula_composer as fc
import roles_state
import tracing

_HELPERS_DIR = Path(__file__).resolve().parents[3] / "core" / "hooks" / "_helpers"
if str(_HELPERS_DIR) not in sys.path:
    sys.path.insert(0, str(_HELPERS_DIR))
import auto_compose  # noqa: E402


def _compose_done_events(agent_dir: Path, session_id: str) -> list[dict]:
    return [
        ev
        for ev in tracing.read_trace(session_id, agent_dir=agent_dir)
        if ev.get("kind") == "compose_done"
    ]


def test_auto_compose_import_does_not_shadow_cognition() -> None:
    """TASK-066: importing auto_compose must not place thinking_os/tools ahead of
    thinking_os on sys.path — otherwise a bare `import cognition` resolves to
    tools/cognition.py (no load_situation_registry) and breaks cos_situation_detect.
    """
    tos = str(auto_compose._THINKING_OS)
    tools = str(Path(auto_compose._THINKING_OS) / "tools")
    if tools in sys.path and tos in sys.path:
        assert sys.path.index(tos) < sys.path.index(tools)
    import importlib

    assert hasattr(importlib.import_module("cognition"), "load_situation_registry")


class TestRecordComposeTraces:
    def test_emits_compose_done_with_chain(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("COS_AGENT_DIR", str(tmp_path))
        signals = fc.signals_from_prompt("audit all security and auth code", "COMPLICATED", 3)
        chain = fc.compose_chain(signals=signals)

        roles_state.record_compose_traces(chain, "ses-rec-1")

        events = _compose_done_events(tmp_path, "ses-rec-1")
        assert len(events) == 1
        assert events[0]["data"]["chain"] == [str(c) for c in chain.chain]
        assert events[0]["data"]["source"] == chain.source

    def test_never_raises_on_bad_chain(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("COS_AGENT_DIR", str(tmp_path))
        # Duck-typed object missing attributes must degrade, not crash.
        roles_state.record_compose_traces(object(), "ses-rec-2")


class TestAutoComposeEmitsTrace:
    def test_compose_roles_stamps_markers_and_emits_trace(self, tmp_path: Path, monkeypatch) -> None:
        agent_dir = tmp_path / "agent"
        panel_dir = agent_dir / "panels" / "p1"
        panel_dir.mkdir(parents=True)
        (panel_dir / "session-id").write_text("ses-auto-1", encoding="utf-8")
        # Traces resolve via COS_AGENT_DIR (agent-level); markers go to panel_dir.
        monkeypatch.setenv("COS_AGENT_DIR", str(agent_dir))

        line = auto_compose._compose_roles("COMPLICATED", 3, str(panel_dir), "audit all security and auth code")

        assert line  # a context line was produced
        assert "[role:" in line  # lead-role directive injected, not just the chain label (TASK-065)
        assert (panel_dir / ".roles").is_file()  # marker → panel (banner)
        events = _compose_done_events(agent_dir, "ses-auto-1")  # trace → agent-level (panel reads)
        assert len(events) == 1
        assert events[0]["data"]["chain"]
