"""Panel-id resolution priority ladder (TASK-035 / Group A).

Verifies src/core/hooks/cos-env.sh::_cos_resolve_panel_id picks the
strongest available signal in the documented order:
  1. caller-set $COS_PANEL_ID env (highest)
  2. adapter env vars in declared order (CLAUDE_SESSION_ID,
     CODEX_SESSION_ID, GEMINI_SESSION_ID, ANTHROPIC_SESSION_ID)
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
    base_env.pop("CLAUDE_CODE_SESSION_ID", None)  # the primary var the resolver leads with
    base_env.pop("CLAUDE_SESSION_ID", None)
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


# ---------------------------------------------------------------------------
# B-epic (TASK-288): panel isolation + ppid-collision detection scenarios.
# Proves the hardening converts a silent cross-panel collision into an
# observed, fail-safe event, and that the common (session-id present) path
# stays clean.
# ---------------------------------------------------------------------------

SESSION_CTX = REPO_ROOT / "src" / "core" / "hooks" / "session-context.sh"
CHECK_STATE = REPO_ROOT / "src" / "core" / "hooks" / "check-state.sh"

_SESSION_VARS = (
    "CLAUDE_CODE_SESSION_ID",
    "CLAUDE_SESSION_ID",
    "CODEX_SESSION_ID",
    "GEMINI_SESSION_ID",
    "ANTHROPIC_SESSION_ID",
)


def _clean_env(env_overrides: dict[str, str]) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("COS_")}
    for k in _SESSION_VARS:
        env.pop(k, None)
    env.update(env_overrides)
    return env


def _source_field(field: str, env_overrides: dict[str, str]) -> str:
    """Source cos-env.sh under controlled env, return an arbitrary exported var."""
    proc = subprocess.run(
        ["bash", "-c", f"source '{COS_ENV}' && printf '%s' \"${{{field}}}\""],
        env=_clean_env(env_overrides),
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout


def _run_session_context(env_overrides: dict[str, str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(SESSION_CTX)],
        input='{"source":"startup"}',
        env=_clean_env(env_overrides),
        capture_output=True,
        text=True,
        timeout=20,
    )


def test_panel_source_classified_ppid_when_no_session_var(tmp_path: Path) -> None:
    # (b) no runtime session-id var -> source classified ppid (the collision risk).
    src = _source_field("COS_PANEL_ID_SOURCE", {"COS_STATE_DIR": str(tmp_path), "COS_AGENT": "claude"})
    assert src == "ppid"


def test_panel_source_classified_session_with_runtime_id(tmp_path: Path) -> None:
    src = _source_field(
        "COS_PANEL_ID_SOURCE",
        {"COS_STATE_DIR": str(tmp_path), "COS_AGENT": "claude", "CLAUDE_CODE_SESSION_ID": "real-uuid-1"},
    )
    assert src == "session"


def test_two_runtime_sessions_isolate_panels(tmp_path: Path) -> None:
    # (a) two distinct runtime session ids -> two distinct panel ids.
    a = _source({"COS_STATE_DIR": str(tmp_path), "COS_AGENT": "claude", "CLAUDE_SESSION_ID": "sess-A"})
    b = _source({"COS_STATE_DIR": str(tmp_path), "COS_AGENT": "claude", "CLAUDE_SESSION_ID": "sess-B"})
    assert a == "sess-A" and b == "sess-B" and a != b


def test_multi_adapter_isolated_agent_dirs(tmp_path: Path) -> None:
    # (e) claude + codex on the same project -> distinct COS_AGENT_DIR.
    claude_dir = _source_field("COS_AGENT_DIR", {"COS_STATE_DIR": str(tmp_path), "COS_AGENT": "claude"})
    codex_dir = _source_field("COS_AGENT_DIR", {"COS_STATE_DIR": str(tmp_path), "COS_AGENT": "codex"})
    assert claude_dir and codex_dir and claude_dir != codex_dir


def test_ppid_fallback_emits_loud_warning(tmp_path: Path) -> None:
    # (b) no runtime session id -> session-context warns LOUD (never silent).
    proc = _run_session_context({"COS_STATE_DIR": str(tmp_path), "COS_AGENT": "claude"})
    assert "ppid fallback" in proc.stderr.lower(), f"expected loud ppid warning; stderr={proc.stderr!r}"


def test_runtime_session_id_no_false_warning(tmp_path: Path) -> None:
    # control: with a real session id the warning must NOT fire.
    proc = _run_session_context(
        {"COS_STATE_DIR": str(tmp_path), "COS_AGENT": "claude", "CLAUDE_CODE_SESSION_ID": "real-sess-xyz"}
    )
    assert "ppid fallback" not in proc.stderr.lower(), f"false alarm; stderr={proc.stderr!r}"


def test_sibling_fossil_rejected_on_session_mismatch(tmp_path: Path) -> None:
    # (d) a state file stamped with a SIBLING panel's session is rejected by check-state.
    panel = tmp_path / "claude" / "panels" / "panelX"
    panel.mkdir(parents=True)
    (panel / "session-id").write_text("ses-claude-CURRENT\n")
    fossil = panel / ".task-current"
    fossil.write_text("ses-claude-OTHER TASK-999\n")  # different session prefix = sibling fossil
    script = f"""
        source '{COS_ENV}' 2>/dev/null
        source '{CHECK_STATE}' 2>/dev/null
        check_state '{fossil}' 86400
        echo "VALID=$STATE_VALID REASON=$STATE_REASON"
    """
    env = _clean_env(
        {
            "COS_STATE_DIR": str(tmp_path),
            "COS_AGENT": "claude",
            "COS_PANEL_ID": "panelX",
            "COS_PANEL_DIR": str(panel),
        }
    )
    proc = subprocess.run(["bash", "-c", script], env=env, capture_output=True, text=True, timeout=20)
    assert "VALID=false" in proc.stdout, f"sibling fossil must be rejected; out={proc.stdout!r}"
    assert "mismatch" in proc.stdout.lower()
