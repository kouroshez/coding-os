"""Per-panel state isolation regression suite (TASK-035).

Covers the contract documented in docs/engineering/state-files.md § S7:
two panels of the SAME agent attached to the same project must never
trample each other's cognitive state files. Files explicitly listed in
$COS_PER_PANEL_FILES route to $COS_PANEL_DIR; all other state stays
shared at $COS_AGENT_DIR / $COS_STATE_DIR.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

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
        ".task-mode",
    ]
    for name in per_panel:
        _write(env, name, "v")
        assert (Path(env["COS_PANEL_DIR"]) / name).exists(), (
            f"{name} should live in panel dir, not agent dir"
        )
        assert not (Path(env["COS_AGENT_DIR"]) / name).exists(), (
            f"{name} must NOT spill into shared agent dir"
        )


def test_shared_files_stay_shared(tmp_path: Path) -> None:
    env = _panel_env(tmp_path, "panel-shared")
    # Files explicitly designed shared (intentionally NOT in COS_PER_PANEL_FILES).
    # .task-mode moved to per-panel (cos-env.sh COS_PER_PANEL_FILES) — banner
    # verbosity must not bleed across panels of the same agent.
    shared = [".model", ".swimlane"]
    for name in shared:
        _write(env, name, "v")
        assert (Path(env["COS_AGENT_DIR"]) / name).exists(), (
            f"{name} must remain in agent dir (panel-agnostic by design)"
        )
        assert not (Path(env["COS_PANEL_DIR"]) / name).exists(), (
            f"{name} must NOT route to panel dir"
        )


def test_cos_current_session_never_falls_back_to_agent_session_id(tmp_path: Path) -> None:
    """Regression lock: cos_current_session() in cos-env.sh must read
    STRICTLY from $COS_SESSION_FILE (panel-private) — never from
    $COS_AGENT_DIR/session-id (the pre-TASK-035 layout). A fossil at
    the agent level belongs to a different panel; trusting it leaks
    that panel's identity into this one's hook log and banner.
    """
    env = _panel_env(tmp_path, "panel-noleak")
    # Plant a competing session-id at the AGENT_DIR level — what a
    # previously session-context.sh:startup would have written.
    agent_session = Path(env["COS_AGENT_DIR"]) / "session-id"
    agent_session.write_text("ses-claude-from-other-panel-XXX")
    # Wipe the panel-private session-id so the AGENT_DIR fossil is the
    # only file present — the worst-case scenario for a leak.
    panel_session = Path(env["COS_PANEL_DIR"]) / "session-id"
    panel_session.unlink()

    script = f"source '{COS_ENV}' && cos_current_session"
    proc = subprocess.run(
        ["bash", "-c", script], env=env, capture_output=True, text=True, check=True
    )
    out = proc.stdout.strip()

    # MUST NOT be the AGENT_DIR fossil. MUST fall back to $COS_PANEL_ID instead.
    assert out != "ses-claude-from-other-panel-XXX", (
        "cos_current_session leaked agent-dir fossil into this panel "
        "(cross-panel identity leak — TASK-035 regression)"
    )
    assert out == env["COS_PANEL_ID"], f"expected fallback to COS_PANEL_ID, got {out!r}"


def test_cos_current_task_never_falls_back_to_agent_dir(tmp_path: Path) -> None:
    """Same protection for cos_current_task() — agent-dir .task-current
    fossils from sibling panels must not surface."""
    env = _panel_env(tmp_path, "panel-task-noleak")
    sid = (Path(env["COS_PANEL_DIR"]) / "session-id").read_text().strip()
    # Plant a fossil at agent dir whose session-id matches the current
    # panel — defeating any naive session-id-based filter; only the scope
    # rule (panel-dir only) should reject it.
    fossil = Path(env["COS_AGENT_DIR"]) / ".task-current"
    fossil.write_text(f"{sid} TASK-FROM-OTHER-PANEL")

    script = f"source '{COS_ENV}' && cos_current_task"
    proc = subprocess.run(
        ["bash", "-c", script], env=env, capture_output=True, text=True, check=True
    )
    out = proc.stdout.strip()
    assert out == "none", (
        f"cos_current_task leaked agent-dir fossil: got {out!r} "
        f"(expected 'none' because the panel-dir has no .task-current)"
    )


def test_no_cross_panel_leak_via_agent_dir_fossil(tmp_path: Path) -> None:
    """Cross-panel leak protection: a fossil .thinking_os-gate sitting at
    $COS_AGENT_DIR (left over by another panel or a pre-TASK-035 writer)
    MUST NOT surface in this panel's read. Reading it would let one
    panel's cognitive state pollute another's banner — the failure mode
    TASK-035 exists to prevent.

    The fossil's session-id deliberately matches a legacy agent-level
    id (matches what cos-env.sh would have produced pre-panel) to prove
    that the rejection is not just a session-mismatch coincidence but a
    deliberate scope rule.
    """
    env = _panel_env(tmp_path, "panel-strict")
    legacy = Path(env["COS_AGENT_DIR"]) / ".thinking_os-gate"
    # Stamp with the panel's session-id to defeat any session-id-based
    # rejection; only the AGENT_DIR-scope rule should stop the read.
    session_id = (Path(env["COS_PANEL_DIR"]) / "session-id").read_text().strip()
    legacy.write_text(f"{session_id} FOSSIL_FROM_OTHER_PANEL 9\n")

    ok, val = _read(env, ".thinking_os-gate")
    assert ok is False, "AGENT_DIR fossil must be ignored to prevent cross-panel leak"
    assert val == ""


def test_panel_dir_takes_precedence_over_legacy(tmp_path: Path) -> None:
    env = _panel_env(tmp_path, "panel-precedence")
    session_id = (Path(env["COS_PANEL_DIR"]) / "session-id").read_text().strip()
    (Path(env["COS_AGENT_DIR"]) / ".thinking_os-gate").write_text(f"{session_id} STALE_LEGACY 9\n")
    _write(env, ".thinking_os-gate", "FRESH_PANEL 2")

    ok, val = _read(env, ".thinking_os-gate")
    assert ok is True
    assert val == "FRESH_PANEL 2"


# ============================================================
# Panel GC (auto-brain-decay.sh tiered cleanup)
# ============================================================

AUTO_BRAIN_DECAY = HOOKS_DIR / "auto-brain-decay.sh"


def _run_gc(env: dict[str, str], panel_id: str) -> None:
    """Force-run auto-brain-decay.sh with debounce bypassed."""
    state_dir = Path(env["COS_STATE_DIR"])
    last_decay = state_dir / ".last-decay"
    if last_decay.exists():
        last_decay.unlink()
    env = {**env, "COS_PANEL_ID": panel_id, "COS_PANEL_DIR": env["COS_PANEL_DIR"]}
    subprocess.run(
        ["bash", str(AUTO_BRAIN_DECAY)],
        env=env,
        input='{"source":"startup"}',
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        timeout=15,
    )


def test_gc_reaps_orphan_panel_without_session_id(tmp_path: Path) -> None:
    """Tier-1 orphan: panel dir created by stray bash invocation (no
    session-id file ever written). Must be reaped after 1 h of inactivity
    so /panels/ doesn't grow without bound during test runs."""
    env = _panel_env(tmp_path, "current-panel")
    panels_root = Path(env["COS_AGENT_DIR"]) / "panels"
    orphan = panels_root / "ppid-orphan-stale"
    orphan.mkdir()
    # No session-id; backdate heartbeat to 2 h old.
    hb = orphan / "heartbeat"
    hb.write_text("0\n")
    old = Path(__file__).stat().st_mtime - 7200
    os.utime(str(hb), (old, old))
    os.utime(str(orphan), (old, old))

    _run_gc(env, "current-panel")
    assert not orphan.exists(), "orphan panel without session-id must be reaped"
    # Current panel must NEVER be reaped — that would self-immolate.
    assert Path(env["COS_PANEL_DIR"]).exists()


def test_gc_keeps_orphan_panel_within_ttl(tmp_path: Path) -> None:
    """Fresh orphan (< 1 h since heartbeat) must stay — test runs and
    sourced shells touch panels constantly; reaping them inside the
    1-hour window would race against legitimate use."""
    env = _panel_env(tmp_path, "current-panel-2")
    panels_root = Path(env["COS_AGENT_DIR"]) / "panels"
    fresh = panels_root / "ppid-orphan-fresh"
    fresh.mkdir()
    (fresh / "heartbeat").write_text(str(int(Path(env["COS_STATE_DIR"]).stat().st_mtime)) + "\n")

    _run_gc(env, "current-panel-2")
    assert fresh.exists(), "fresh orphan within TTL must survive GC"


def test_gc_keeps_real_panel_with_recent_heartbeat(tmp_path: Path) -> None:
    """Tier-2 real panel (has session-id) is kept while heartbeat is fresh
    (default 24 h window). Verifies the GC does NOT prematurely reap live
    panels just because they're not the current panel."""
    env = _panel_env(tmp_path, "current-panel-3")
    panels_root = Path(env["COS_AGENT_DIR"]) / "panels"
    live = panels_root / "panel-live"
    live.mkdir()
    (live / "session-id").write_text("ses-claude-live-test\n")
    import time

    (live / "heartbeat").write_text(f"{int(time.time())}\n")

    _run_gc(env, "current-panel-3")
    assert live.exists(), "live panel with recent heartbeat must survive GC"


# ============================================================
# Worktree state routing (TASK-515 / pr-mode) — cos-env.sh § worktree block
# Every worktree of one repo must share the MAIN repo's COS_STATE_DIR, and a
# command that would bind worktree state to the global hub must be refused.
# ============================================================

_COS_ROUTING_VARS = (
    "COS_STATE_DIR",
    "COS_PROJECT_ROOT",
    "COS_DB_PATH",
    "COS_AGENT_DIR",
    "COS_PANEL_DIR",
    "COS_PANEL_ID",
    "COS_SESSION_FILE",
    "CLAUDE_PROJECT_DIR",
    "COS_STATE_MISROUTE",
    "COS_WORKTREE_ROOT",
    "COS_GIT_WORKFLOW",
    "COS_GIT_INTEGRATION_BRANCH",
    "COS_GIT_PROTECTED_BRANCHES",
)


def _clean_env() -> dict[str, str]:
    """Env stripped of inherited coding-os routing vars so cos-env.sh resolves
    COS_STATE_DIR from scratch — the real worktree-command condition."""
    return {k: v for k, v in os.environ.items() if k not in _COS_ROUTING_VARS}


def _resolve_state_dir(env: dict[str, str], cwd: Path) -> tuple[str, str]:
    """Source cos-env.sh with env+cwd; return (COS_STATE_DIR, COS_STATE_MISROUTE)."""
    script = (
        f"source '{COS_ENV}' 2>/dev/null; "
        'printf "%s|%s" "$COS_STATE_DIR" "${COS_STATE_MISROUTE:-}"'
    )
    proc = subprocess.run(
        ["bash", "-c", script], env=env, cwd=str(cwd), capture_output=True, text=True
    )
    out = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else "|"
    state_dir, _, misroute = out.partition("|")
    return state_dir, misroute


def test_worktree_project_root_beats_claude_project_dir(tmp_path: Path) -> None:
    """Given-1: cwd under a worktrees/ path + COS_PROJECT_ROOT exported to the
    main repo => COS_STATE_DIR is the MAIN repo's .coding-os, even when
    CLAUDE_PROJECT_DIR points at the worktree itself. This is the shared-state
    guarantee every sibling worktree of the repo relies on."""
    main_repo = tmp_path / "main"
    (main_repo / ".coding-os").mkdir(parents=True)
    wt = tmp_path / ".coding-os" / "worktrees" / "slug" / "task-1"
    wt.mkdir(parents=True)

    env = _clean_env()
    env["COS_PROJECT_ROOT"] = str(main_repo)
    env["CLAUDE_PROJECT_DIR"] = str(wt)  # runtime points it at the worktree; must NOT win
    state_dir, misroute = _resolve_state_dir(env, wt)

    assert state_dir == str(main_repo / ".coding-os"), (
        f"worktree state must route to main repo, got {state_dir!r}"
    )
    assert misroute == "", "happy path must not flag a misroute"


def test_worktree_misroute_to_hub_is_refused(tmp_path: Path) -> None:
    """Given-2: cwd under a worktrees/ path with NO COS_PROJECT_ROOT and no
    resolvable git main repo, inheriting the hub's COS_STATE_DIR
    ($HOME/.coding-os). cos-env.sh must REFUSE — flag COS_STATE_MISROUTE and
    steer off the hub — never silently bind worktree state to the global hub."""
    fake_home = tmp_path / "home"
    hub = fake_home / ".coding-os"
    wt = hub / "worktrees" / "slug" / "task-1"
    wt.mkdir(parents=True)

    env = _clean_env()
    env["HOME"] = str(fake_home)
    env["COS_STATE_DIR"] = str(hub)  # inherited from `cos hub`; not a git repo => refuse
    state_dir, misroute = _resolve_state_dir(env, wt)

    assert misroute == "1", "misroute to the global hub must be flagged"
    assert state_dir != str(hub), "must not silently bind worktree state to the hub"


def test_worktree_git_recovery_without_project_root(tmp_path: Path) -> None:
    """A real git worktree with NO COS_PROJECT_ROOT => cos-env.sh recovers the
    main repo via `git rev-parse --git-common-dir` and routes state there."""
    main_repo = tmp_path / "repo"
    main_repo.mkdir()
    (main_repo / ".coding-os").mkdir()
    git = ["git", "-c", "user.email=t@t", "-c", "user.name=t"]
    subprocess.run([*git, "init", "-q"], cwd=main_repo, check=True)
    subprocess.run([*git, "commit", "-q", "--allow-empty", "-m", "init"], cwd=main_repo, check=True)
    wt = tmp_path / ".coding-os" / "worktrees" / "slug" / "wt"
    wt.parent.mkdir(parents=True)
    subprocess.run([*git, "worktree", "add", "-q", str(wt)], cwd=main_repo, check=True)

    env = _clean_env()
    state_dir, misroute = _resolve_state_dir(env, wt)

    assert os.path.realpath(state_dir) == os.path.realpath(str(main_repo / ".coding-os")), (
        f"git-recovered worktree state must route to main repo, got {state_dir!r}"
    )
    assert misroute == "", "git recovery is not a misroute"


# ============================================================
# pr-mode enablement (TASK-518) — cos-env.sh reads hub-settings.json
# git_settings.enabled and exports COS_GIT_WORKFLOW=pr (+ branch policy).
# ============================================================


def _resolve_git_env(env: dict[str, str], cwd: Path) -> tuple[str, str, str]:
    script = (
        f"source '{COS_ENV}' 2>/dev/null; "
        'printf "%s|%s|%s" "${COS_GIT_WORKFLOW:-}" '
        '"${COS_GIT_INTEGRATION_BRANCH:-}" "${COS_GIT_PROTECTED_BRANCHES:-}"'
    )
    proc = subprocess.run(
        ["bash", "-c", script], env=env, cwd=str(cwd), capture_output=True, text=True
    )
    out = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else "||"
    workflow, integration, protected = ([*out.split("|"), "", "", ""])[:3]
    return workflow, integration, protected


def test_pr_mode_enabled_exports_workflow_and_policy(tmp_path: Path) -> None:
    """git_settings.enabled=true => COS_GIT_WORKFLOW=pr plus the integration +
    protected branch policy, so every hook process sees the mode (§1)."""
    state = tmp_path / ".coding-os"
    state.mkdir(parents=True)
    (state / "hub-settings.json").write_text(
        json.dumps(
            {
                "git_settings": {
                    "enabled": True,
                    "integration_branch": "develop",
                    "protected_branches": ["production", "release"],
                }
            }
        )
    )
    env = _clean_env()
    env["COS_STATE_DIR"] = str(state)
    workflow, integration, protected = _resolve_git_env(env, tmp_path)
    assert workflow == "pr"
    assert integration == "develop"
    assert protected == "production,release"


def test_pr_mode_disabled_stays_trunk(tmp_path: Path) -> None:
    state = tmp_path / ".coding-os"
    state.mkdir(parents=True)
    (state / "hub-settings.json").write_text(json.dumps({"git_settings": {"enabled": False}}))
    env = _clean_env()
    env["COS_STATE_DIR"] = str(state)
    workflow, _, _ = _resolve_git_env(env, tmp_path)
    assert workflow == "", "disabled git_settings must NOT export COS_GIT_WORKFLOW"


def test_pr_mode_explicit_env_wins_over_settings(tmp_path: Path) -> None:
    """An explicitly-exported COS_GIT_WORKFLOW is authoritative (the enablement
    only fills an UNSET var) — never silently overridden by hub-settings.json."""
    state = tmp_path / ".coding-os"
    state.mkdir(parents=True)
    (state / "hub-settings.json").write_text(json.dumps({"git_settings": {"enabled": True}}))
    env = _clean_env()
    env["COS_STATE_DIR"] = str(state)
    env["COS_GIT_WORKFLOW"] = "trunk"
    workflow, _, _ = _resolve_git_env(env, tmp_path)
    assert workflow == "trunk"
