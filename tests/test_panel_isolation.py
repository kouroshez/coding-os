"""Per-panel state isolation regression suite (TASK-035).

Covers the contract documented in docs/engineering/state-files.md § S7:
two panels of the SAME agent attached to the same project must never
trample each other's cognitive state files. Files explicitly listed in
$COS_PER_PANEL_FILES route to $COS_PANEL_DIR; all other state stays
shared at $COS_AGENT_DIR / $COS_STATE_DIR.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "src" / "core" / "hooks"
WRITE_STATE = HOOKS_DIR / "write-state.sh"
CHECK_STATE = HOOKS_DIR / "check-state.sh"
COS_ENV = HOOKS_DIR / "cos-env.sh"


def _panel_env(tmp_path: Path, panel_id: str, agent: str = "claude") -> dict[str, str]:
    state_dir = tmp_path / ".coding-os"
    agent_dir = state_dir / agent
    panel_dir = agent_dir / "panels" / panel_id
    panel_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update(
        {
            "COS_STATE_DIR": str(state_dir),
            "COS_AGENT": agent,
            "COS_AGENT_DIR": str(agent_dir),
            "COS_PANEL_ID": panel_id,
            "COS_PANEL_DIR": str(panel_dir),
            "COS_SESSION_FILE": str(panel_dir / "session-id"),
            "COS_DB_PATH": str(state_dir / "coding-os.db"),
        }
    )
    # Seed a session-id so write-state.sh produces a usable prefix.
    (panel_dir / "session-id").write_text(f"ses-{agent}-{panel_id}")
    return env


def _write(env: dict[str, str], state_file: str, value: str) -> None:
    subprocess.run(
        ["bash", str(WRITE_STATE), state_file, value],
        env=env,
        check=True,
        cwd=str(REPO_ROOT),
    )


def _read(env: dict[str, str], state_file: str) -> tuple[bool, str]:
    script = f"""
source '{COS_ENV}' 2>/dev/null
source '{CHECK_STATE}' 2>/dev/null
check_state '{state_file}' 7200
echo "$STATE_VALID|$STATE_VALUE"
"""
    proc = subprocess.run(
        ["bash", "-c", script],
        env=env,
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    line = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else "|"
    valid, _, value = line.partition("|")
    return valid == "true", value


def test_two_panels_independent_gate(tmp_path: Path) -> None:
    env_a = _panel_env(tmp_path, "panel-A")
    env_b = _panel_env(tmp_path, "panel-B")

    _write(env_a, ".thinking_os-gate", "COMPLICATED 4")
    _write(env_b, ".thinking_os-gate", "CLEAR 1")

    ok_a, val_a = _read(env_a, ".thinking_os-gate")
    ok_b, val_b = _read(env_b, ".thinking_os-gate")

    assert ok_a is True, "panel A must read its own gate"
    assert val_a == "COMPLICATED 4"
    assert ok_b is True, "panel B must read its own gate"
    assert val_b == "CLEAR 1"

    # Disk topology: each panel dir holds its own file; no shared collision.
    assert (Path(env_a["COS_PANEL_DIR"]) / ".thinking_os-gate").exists()
    assert (Path(env_b["COS_PANEL_DIR"]) / ".thinking_os-gate").exists()


def test_panel_cognitive_files_route_to_panel_dir(tmp_path: Path) -> None:
    env = _panel_env(tmp_path, "panel-cog")
    per_panel = [
        ".thinking_os-gate",
        ".task-current",
        ".active-skill",
        ".doc-anchor",
        ".memory-check",
        ".zoom-checkpoint",
        ".active-formula",
        ".learn-suggestions",
    ]
    for name in per_panel:
        _write(env, name, "v")
        assert (Path(env["COS_PANEL_DIR"]) / name).exists(), \
            f"{name} should live in panel dir, not agent dir"
        assert not (Path(env["COS_AGENT_DIR"]) / name).exists(), \
            f"{name} must NOT spill into shared agent dir"


def test_shared_files_stay_shared(tmp_path: Path) -> None:
    env = _panel_env(tmp_path, "panel-shared")
    # Files explicitly designed shared (intentionally NOT in COS_PER_PANEL_FILES).
    shared = [".task-mode", ".model", ".swimlane"]
    for name in shared:
        _write(env, name, "v")
        assert (Path(env["COS_AGENT_DIR"]) / name).exists(), \
            f"{name} must remain in agent dir (panel-agnostic by design)"
        assert not (Path(env["COS_PANEL_DIR"]) / name).exists(), \
            f"{name} must NOT route to panel dir"


def test_legacy_agent_dir_fallback_on_read(tmp_path: Path) -> None:
    """Migration safety: hooks pre-dating per-panel still write to AGENT_DIR.
    Readers must surface the fossil for one cycle so consumer projects don't
    see "Session mismatch" spam during the upgrade window.
    """
    env = _panel_env(tmp_path, "panel-legacy")
    session_id = (Path(env["COS_PANEL_DIR"]) / "session-id").read_text().strip()
    legacy = Path(env["COS_AGENT_DIR"]) / ".thinking_os-gate"
    legacy.write_text(f"{session_id} COMPLICATED 3\n")

    ok, val = _read(env, ".thinking_os-gate")
    assert ok is True
    assert val == "COMPLICATED 3"


def test_panel_dir_takes_precedence_over_legacy(tmp_path: Path) -> None:
    env = _panel_env(tmp_path, "panel-precedence")
    session_id = (Path(env["COS_PANEL_DIR"]) / "session-id").read_text().strip()
    (Path(env["COS_AGENT_DIR"]) / ".thinking_os-gate").write_text(
        f"{session_id} STALE_LEGACY 9\n"
    )
    _write(env, ".thinking_os-gate", "FRESH_PANEL 2")

    ok, val = _read(env, ".thinking_os-gate")
    assert ok is True
    assert val == "FRESH_PANEL 2"
