"""Unit tests for adapters.claude.sdk_dispatcher._presence_write.

PURPOSE: The SDK dispatcher spawns formula sub-agents in-process via
         claude_agent_sdk.query() and must surface their liveness on the
         board's live-agents panel.  It does this by writing the same
         presence JSON format that core/hooks/agent-presence.sh produces
         for shell-hook-driven sessions.

         This test guards:
           1. the payload shape stays in lock-step with agent-presence.sh
           2. lifecycle merges preserve prior fields (start → tool → stop
              → end doesn't clobber started_at)
           3. atomic write leaves no .tmp.* garbage after success
           4. corrupt prior file is recovered (written cleanly, not crashed)

INPUT:   tmp_path-scoped project root.
OUTPUT:  Assertions on the json file.
NOTES:   Imports the dispatcher module by path so the test doesn't need
         the claude-agent-sdk extra installed.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_dispatcher_module():
    """Load adapters/claude/sdk_dispatcher.py by path (no extras required).

    The top-level `from dispatcher import ...` only needs
    core/thinking_os on sys.path, which the module does itself. The
    `import claude_agent_sdk` lives inside ClaudeSDKDispatcher.dispatch()
    and so is NOT executed by `_presence_write`.
    """
    spec = importlib.util.spec_from_file_location(
        "coding_os_sdk_dispatcher_under_test",
        _REPO_ROOT / "adapters" / "claude" / "sdk_dispatcher.py",
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    # Ensure thinking_os is importable (module does this too, belt-and-braces).
    tos = _REPO_ROOT / "core" / "thinking_os"
    if str(tos) not in sys.path:
        sys.path.insert(0, str(tos))
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def dispatcher_mod():
    return _load_dispatcher_module()


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / ".coding-os").mkdir(parents=True)
    return tmp_path


def _presence_file(project: Path, sid: str) -> Path:
    return project / ".coding-os" / "claude" / "sessions" / f"{sid}.json"


def test_write_start_creates_file_with_expected_schema(dispatcher_mod, project: Path):
    sid = "ses-claude-sdk-F5-1777030000-12345"
    dispatcher_mod._presence_write(project, "claude", sid, "start", pid=4242)

    path = _presence_file(project, sid)
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    # Schema parity with core/hooks/agent-presence.sh
    assert set(data.keys()) == {
        "agent", "session_id", "pid",
        "started_at", "last_prompt_at", "last_tool_at",
        "last_stop_at", "ended_at",
    }
    assert data["agent"] == "claude"
    assert data["session_id"] == sid
    assert data["pid"] == 4242
    assert isinstance(data["started_at"], int)
    assert data["last_tool_at"] is None
    assert data["ended_at"] is None


def test_lifecycle_preserves_started_at(dispatcher_mod, project: Path):
    """start → tool → stop → end must leave started_at untouched."""
    sid = "ses-claude-sdk-F1-1-100"
    dispatcher_mod._presence_write(project, "claude", sid, "start", pid=1)
    initial = json.loads(_presence_file(project, sid).read_text())["started_at"]

    for event in ("tool", "stop", "end"):
        dispatcher_mod._presence_write(project, "claude", sid, event, pid=1)

    final = json.loads(_presence_file(project, sid).read_text())
    assert final["started_at"] == initial
    assert final["last_tool_at"] is not None
    assert final["last_stop_at"] is not None
    assert final["ended_at"] is not None


def test_atomic_write_leaves_no_tmp_garbage(dispatcher_mod, project: Path):
    sid = "ses-claude-sdk-F2-2-200"
    dispatcher_mod._presence_write(project, "claude", sid, "start", pid=2)
    dispatcher_mod._presence_write(project, "claude", sid, "tool", pid=2)

    sessions_dir = project / ".coding-os" / "claude" / "sessions"
    tmp_leftovers = list(sessions_dir.glob(f"{sid}.tmp.*"))
    assert tmp_leftovers == [], f"tmp files leaked: {tmp_leftovers}"


def test_corrupt_prior_file_is_overwritten_cleanly(dispatcher_mod, project: Path):
    sid = "ses-claude-sdk-F3-3-300"
    path = _presence_file(project, sid)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("not-json {{{", encoding="utf-8")

    dispatcher_mod._presence_write(project, "claude", sid, "start", pid=3)

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["session_id"] == sid
    assert data["pid"] == 3


def test_double_end_is_idempotent(dispatcher_mod, project: Path):
    """try/finally in the dispatcher may call end on both the happy path
    AND an already-terminal path; subsequent end must not corrupt state."""
    sid = "ses-claude-sdk-F4-4-400"
    dispatcher_mod._presence_write(project, "claude", sid, "start", pid=4)
    dispatcher_mod._presence_write(project, "claude", sid, "stop", pid=4)
    dispatcher_mod._presence_write(project, "claude", sid, "end", pid=4)
    first = json.loads(_presence_file(project, sid).read_text())["ended_at"]

    dispatcher_mod._presence_write(project, "claude", sid, "end", pid=4)
    second = json.loads(_presence_file(project, sid).read_text())["ended_at"]
    # `end` overwrites with the current timestamp each time — that's fine;
    # the invariant is "second >= first and still an int".
    assert isinstance(second, int) and second >= first
