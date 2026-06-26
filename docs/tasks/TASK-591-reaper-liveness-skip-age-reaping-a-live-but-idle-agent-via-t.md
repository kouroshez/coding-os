---
id: TASK-591
title: "Reaper liveness: skip age-reaping a live-but-idle agent via the worktree lock-reason pid@host (no in-worktree marker)"
swimlane: infra
kind: bug
epic: git-foundation-hardening
labels: [pr-mode, reaper, concurrency, split-from-585, ready]
status: icebox
priority: P3
appetite: 1d
created: 2026-06-26
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-591: Reaper liveness: skip age-reaping a live-but-idle agent via the worktree lock-reason pid@host (no in-worktree marker)

**Outcome (one sentence):** Split out of TASK-585. The reaper's 'unknown'-state age-fallback (_session_state returns 'unknown' when no presence record exists; reapable when _worktree_stale past 24h) can reap a still-alive agent whose presence record is missing — work is bundle-preserved first (so disruption, not data-loss, per the over-engineering critic), but a live agent's worktree+branch still vanish. Fix without an in-worktree .pr-owner file (which `git add -A` would commit into the PR): stamp the owner pid@host into the EXISTING `git worktree lock --reason` at `cos pr open` (pr_commands.py:~402), and in the reaper's 'unknown'+stale branch read the lock reason and skip when that pid is alive same-host (reuse presence.pid_alive). Reuses the already-present worktree lock; no new state file, no commit risk.

## Read First
- src/cli/pr_commands.py
- src/core/board_os/presence.py
- docs/playbooks/pr-workflow.md

## Repro Steps
Start a pr-mode worktree agent; remove/withhold its presence session JSON under <main>/.coding-os/*/sessions/; leave the worktree idle >COS_PR_ORPHAN_MAX_AGE (default 24h). A sibling SessionStart fires pr-reap → the live agent's worktree+branch are GC'd (work survives only as a bundle in ~/.coding-os/reaped/ the agent never checks).

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** a pr-mode worktree whose presence record is absent but whose owner pid (from the worktree lock reason) is alive on this host, **When** the reaper sweeps past COS_PR_ORPHAN_MAX_AGE, **Then** it does NOT reap it. **Given** the owner pid is dead (or a foreign host), **When** the worktree is stale, **Then** it is reaped (work preserved first, unchanged). **Given** a legacy worktree with a lock reason lacking pid@host, **When** the reaper runs, **Then** behavior is unchanged (back-compat — falls through to the existing stale check). Verify: uv run pytest tests/test_cli.py::TestCosPr -q green + a new reaper test.

## Work Log
- 2026-06-26 [claude]: DESIGN BLOCKER found (deferred, not rushed — same class as TASK-590/585a). The task premise 'stamp owner pid@host at…
