---
id: TASK-585
title: "Fix multi-agent git concurrency robustness: test-governor PID lock + misroute banner surfacing + reaper liveness PID-stamp"
swimlane: infra
kind: bug
epic: git-foundation-hardening
labels: [git, concurrency, pr-mode, reaper, ready]
status: icebox
priority: P2
appetite: 1d
created: 2026-06-26
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-585: Fix multi-agent git concurrency robustness: test-governor PID lock + misroute banner surfacing + reaper liveness PID-stamp

**Outcome (one sentence):** Three concurrency footguns under many-agents-one-machine: (1) test-governor decides lock-held via host-global `pgrep -f pytest` with no PID in the lock — cross-repo phantom-hold + pytest-xdist false-clear; (2) the COS_STATE_MISROUTE quarantine silently binds a worktree session's cognitive state to an empty orphan dir (warned once to stderr); (3) the reaper's age-fallback can reap a still-alive agent whose presence record is missing (work is bundled first, so disruption not loss).

## Read First
- src/core/hooks/test-governor.sh
- src/core/hooks/cos-env.sh
- src/cli/pr_commands.py
- src/core/hooks/session-context.sh
- src/core/board_os/presence.py

## Repro Steps
1) test-governor: write .test-run.lock with started_ts older than grace from repo A, finish repo A's pytest, start any pytest elsewhere on host → repo A sees HELD=true (false phantom-hold). 2) misroute: create a worktree at a custom path without exporting COS_PROJECT_ROOT and run a hook where git-common-dir resolution fails → COS_STATE_DIR binds to ~/.coding-os-misrouted/<cksum>, banner stays silent after turn 1. 3) reaper: pr-mode worktree, remove its presence json, leave idle >COS_PR_ORPHAN_MAX_AGE → a sibling SessionStart reap GCs the live agent's worktree.

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** two repos each able to run pytest, **When** repo A's pytest has finished but repo B's is running, **Then** repo A's .test-run.lock is NOT falsely reported held (HELD gates on the recorded holder pid_alive AND same-host, with the PID written into the lock JSON). **Given** COS_STATE_MISROUTE=1, **When** any turn's USER_BANNER renders, **Then** it carries a ⚠️ state-misrouted marker every turn (not once-to-stderr). **Given** a pr-mode worktree whose presence record is absent but whose owner pid is alive on this host, **When** the reaper sweeps past the age window, **Then** it does NOT reap it (pid_alive skip via a .pr-owner stamp written at `cos pr open`). Verify: make verify-hooks green AND uv run pytest tests/test_cli.py::TestCosPr -q green.

## Work Log
