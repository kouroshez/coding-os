"""Panel-id resolution priority ladder (TASK-035 / Group A).

Verifies src/core/hooks/cos-env.sh::_cos_resolve_panel_id picks the
strongest available signal in the documented order:
  1. caller-set $COS_PANEL_ID env (highest)
  2. adapter env vars in declared order (CLAUDE_SESSION_ID,
     CURSOR_SESSION_ID, CURSOR_TRACE_ID, CODEX_SESSION_ID,
     GEMINI_SESSION_ID, ANTHROPIC_SESSION_ID)
  3. PPID-derived hash fallback (lowest)

Also asserts cos_panel_upgrade_from_payload swaps the panel id when the
agent hook stdin payload carries a session_id field.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
COS_ENV = REPO_ROOT / "src" / "core" / "hooks" / "cos-env.sh"


def _source(env_overrides: dict[str, str]) -> str:
    """Source cos-env.sh under controlled env, return COS_PANEL_ID."""
    base_env = {k: v for k, v in os.environ.items() if not k.startswith("COS_")}
    base_env.pop("CLAUDE_SESSION_ID", None)
    base_env.pop("CURSOR_SESSION_ID", None)
    base_env.pop("CURSOR_TRACE_ID", None)
    base_env.pop("CODEX_SESSION_ID", None)
    base_env.pop("GEMINI_SESSION_ID", None)
    base_env.pop("ANTHROPIC_SESSION_ID", None)
    base_env.update(env_overrides)
    proc = subprocess.run(
        ["bash", "-c", f"source '{COS_ENV}' && printf '%s' \"$COS_PANEL_ID\""],
        env=base_env,
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout


def test_explicit_panel_id_env_wins(tmp_path: Path) -> None:
    pid = _source(
        {
            "COS_STATE_DIR": str(tmp_path),
            "COS_AGENT": "claude",
            "COS_PANEL_ID": "explicit-override",
            "CLAUDE_SESSION_ID": "should-be-ignored",
        }
    )
    assert pid == "explicit-override"


def test_claude_session_id_env(tmp_path: Path) -> None:
    pid = _source(
        {
            "COS_STATE_DIR": str(tmp_path),
            "COS_AGENT": "claude",
            "CLAUDE_SESSION_ID": "abc123-claude-uuid",
        }
    )
    assert pid == "abc123-claude-uuid"


def test_codex_session_id_env(tmp_path: Path) -> None:
    pid = _source(
        {
            "COS_STATE_DIR": str(tmp_path),
            "COS_AGENT": "codex",
            "CODEX_SESSION_ID": "codex-xyz",
        }
    )
    assert pid == "codex-xyz"


def test_cursor_trace_id_env(tmp_path: Path) -> None:
    pid = _source(
        {
            "COS_STATE_DIR": str(tmp_path),
            "COS_AGENT": "cursor",
            "CURSOR_TRACE_ID": "trace-789",
        }
    )
    assert pid == "trace-789"


def test_ppid_fallback_when_no_env(tmp_path: Path) -> None:
    pid = _source({"COS_STATE_DIR": str(tmp_path), "COS_AGENT": "claude"})
    # Last-resort fallback emits ppid-<8hex> or ppid-<pid>; never empty.
    assert pid.startswith("ppid-")
    assert len(pid) > len("ppid-")


def test_sanitization_strips_unsafe_chars(tmp_path: Path) -> None:
    pid = _source(
        {
            "COS_STATE_DIR": str(tmp_path),
            "COS_AGENT": "claude",
            "CLAUDE_SESSION_ID": "ab/c:d e!f",
        }
    )
    # Only [A-Za-z0-9_.-] survive; the rest become dashes.
    assert "/" not in pid
    assert ":" not in pid
    assert " " not in pid
    assert "!" not in pid


def test_stdin_upgrade_swaps_panel(tmp_path: Path) -> None:
    """cos_panel_upgrade_from_payload upgrades to stdin session_id."""
    script = f"""
        source '{COS_ENV}' 2>/dev/null
        before="$COS_PANEL_ID"
        cos_panel_upgrade_from_payload '{{"session_id":"stdin-panel-xyz"}}'
        after="$COS_PANEL_ID"
        echo "$before|$after"
    """
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith("COS_") and "SESSION_ID" not in k and "TRACE_ID" not in k
    }
    env.update({"COS_STATE_DIR": str(tmp_path), "COS_AGENT": "claude"})
    proc = subprocess.run(
        ["bash", "-c", script], env=env, capture_output=True, text=True, check=True
    )
    line = proc.stdout.strip().splitlines()[-1]
    before, after = line.split("|", 1)
    assert before != after
    assert after == "stdin-panel-xyz"


def test_stdin_upgrade_noop_on_missing_field(tmp_path: Path) -> None:
    script = f"""
        source '{COS_ENV}' 2>/dev/null
        before="$COS_PANEL_ID"
        cos_panel_upgrade_from_payload '{{"other_field":"foo"}}'
        echo "$before|$COS_PANEL_ID"
    """
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith("COS_") and "SESSION_ID" not in k and "TRACE_ID" not in k
    }
    env.update({"COS_STATE_DIR": str(tmp_path), "COS_AGENT": "claude"})
    proc = subprocess.run(
        ["bash", "-c", script], env=env, capture_output=True, text=True, check=True
    )
    line = proc.stdout.strip().splitlines()[-1]
    before, after = line.split("|", 1)
    assert before == after
