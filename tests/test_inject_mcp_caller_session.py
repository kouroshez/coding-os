"""inject-mcp-caller-session.sh — PreToolUse hook that threads the calling
panel's coding-os session into MCP task-tool args (agent_session) so the
panel-blind MCP server attributes the write to the real caller (TASK-212).

Contract under test:
- inject: no agent_session in args -> emit hookSpecificOutput.updatedInput
  equal to the original tool_input plus the panel's session-id (merge only).
- no-override: caller already passed agent_session -> emit NOTHING.
- fail-open: panel session unresolvable -> emit NOTHING, exit 0.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOOK = REPO / "src" / "core" / "hooks" / "inject-mcp-caller-session.sh"
SID = "ses-claude-20990101-000000-t211"


def _env(state_dir: Path, panel_id: str) -> dict:
    env = dict(os.environ)
    # Drop inherited runtime session vars so the explicit COS_PANEL_ID wins
    # deterministically (rung #1 of the resolver) instead of the live session.
    for k in ("CLAUDE_CODE_SESSION_ID", "CLAUDE_SESSION_ID", "CURSOR_SESSION_ID", "CODEX_SESSION_ID"):
        env.pop(k, None)
    env["COS_STATE_DIR"] = str(state_dir)
    env["COS_AGENT"] = "claude"
    env["COS_PANEL_ID"] = panel_id
    return env


def _seed_panel(tmp_path: Path, panel_id: str, sid: str | None) -> Path:
    state = tmp_path / "state"
    (state).mkdir(parents=True, exist_ok=True)
    (state / ".agent").write_text("claude\n")
    panel = state / "claude" / "panels" / panel_id
    panel.mkdir(parents=True, exist_ok=True)
    if sid is not None:
        (panel / "session-id").write_text(sid + "\n")
    return state


def _run(state: Path, panel_id: str, payload: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=20,
        env=_env(state, panel_id),
        cwd=str(REPO),
    )


def test_injects_panel_session_when_absent(tmp_path: Path) -> None:
    state = _seed_panel(tmp_path, "panel-A", SID)
    payload = {"tool_name": "mcp__coding-os__cos_task_move", "tool_input": {"task_id": "TASK-1", "to": "in_progress"}}
    proc = _run(state, "panel-A", payload)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip(), f"expected updatedInput JSON, got empty (stderr={proc.stderr!r})"
    out = json.loads(proc.stdout)
    updated = out["hookSpecificOutput"]["updatedInput"]
    assert updated["agent_session"] == SID
    # merge-only: original fields preserved, nothing else touched
    assert updated["task_id"] == "TASK-1"
    assert updated["to"] == "in_progress"


def test_does_not_override_explicit_agent_session(tmp_path: Path) -> None:
    state = _seed_panel(tmp_path, "panel-B", SID)
    payload = {
        "tool_name": "mcp__coding-os__cos_task_move",
        "tool_input": {"task_id": "TASK-2", "to": "testing", "agent_session": "ses-claude-explicit-xyz"},
    }
    proc = _run(state, "panel-B", payload)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "", f"must NOT override an explicit agent_session; got {proc.stdout!r}"


def test_fail_open_when_session_unresolvable(tmp_path: Path) -> None:
    # Panel dir exists but has no session-id file -> cos_current_session empty.
    state = _seed_panel(tmp_path, "panel-C", sid=None)
    payload = {"tool_name": "mcp__coding-os__cos_task_move", "tool_input": {"task_id": "TASK-3", "to": "in_progress"}}
    proc = _run(state, "panel-C", payload)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "", f"fail-open: no session -> emit nothing; got {proc.stdout!r}"


def _path_without_jq(tmp_path: Path) -> str:
    """A PATH with every tool symlinked EXCEPT jq — reliably simulates a jq-less host."""
    bindir = tmp_path / "nojq-bin"
    bindir.mkdir()
    seen: set[str] = set()
    for d in os.environ.get("PATH", "").split(os.pathsep):
        dp = Path(d)
        if not dp.is_dir():
            continue
        for entry in dp.iterdir():
            if entry.name == "jq" or entry.name in seen:
                continue
            try:
                (bindir / entry.name).symlink_to(entry)
                seen.add(entry.name)
            except OSError:
                pass
    return str(bindir)


def test_jq_missing_fails_loud_not_silent(tmp_path: Path) -> None:
    # (TASK-287) jq absent must NOT silently exit 0 — it must warn LOUD + drop a
    # diagnostic marker, while still letting the MCP call proceed (never block).
    state = _seed_panel(tmp_path, "panel-D", SID)
    env = _env(state, "panel-D")
    env["PATH"] = _path_without_jq(tmp_path)
    payload = {"tool_name": "mcp__coding-os__cos_task_move", "tool_input": {"task_id": "TASK-4", "to": "in_progress"}}
    proc = subprocess.run(
        ["bash", str(HOOK)], input=json.dumps(payload), capture_output=True, text=True, timeout=20, env=env, cwd=str(REPO)
    )
    assert proc.returncode == 0, f"must not block the MCP call; rc={proc.returncode} stderr={proc.stderr!r}"
    assert "jq not found" in proc.stderr.lower(), f"jq-missing must warn LOUD; stderr={proc.stderr!r}"
    marker = state / "claude" / "panels" / "panel-D" / ".mcp-attribution-degraded"
    assert marker.exists(), "jq-missing must drop a diagnostic marker"
    # debounced: a second call in the same panel does not re-warn on stderr
    proc2 = subprocess.run(
        ["bash", str(HOOK)], input=json.dumps(payload), capture_output=True, text=True, timeout=20, env=env, cwd=str(REPO)
    )
    assert "jq not found" not in proc2.stderr.lower(), f"warning must be debounced; stderr={proc2.stderr!r}"
