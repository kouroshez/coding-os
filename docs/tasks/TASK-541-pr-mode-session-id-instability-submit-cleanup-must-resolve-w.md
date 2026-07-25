---
id: TASK-541
title: "pr-mode session-id instability: submit/cleanup must resolve worktree+branch from disk (not re-derive)"
swimlane: core
kind: bug
epic: multi-agent-pr-mode
labels: [ready]
status: archive
priority: P1
appetite: 1d
created: 2026-06-24
started: 2026-06-24
completed: 2026-06-24
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-541: pr-mode session-id instability: submit/cleanup must resolve worktree+branch from disk (not re-derive)

**Outcome (one sentence):** `cos pr submit` and `cos pr cleanup` operate on the worktree+branch that `cos pr open` actually created, even when the session id differs between invocations (the `pid-<getpid>` fallback at pr_commands.py:118 yields a different value per process when no COS_AGENT_SESSION_ID/COS_PANEL_ID is set). They resolve from disk — the way the reaper already does (pr_commands.py:859) — instead of re-deriving `_branch_for(task_slug, session)`. Fast-path preserved when the computed worktree exists; ambiguous (multiple worktrees for one task) falls back to the computed pair so the caller's existence check still surfaces a clear error.

## Read First
- src/cli/pr_commands.py
- docs/playbooks/pr-workflow.md

## Repro Steps
1. Unset COS_AGENT_SESSION_ID + COS_PANEL_ID. 2. `cos pr open --task TASK-X` in process P1 → session=pid-<P1>, creates worktree `TASK-X-pid-<P1>` + branch `agents/TASK-X/pid-<P1>`. 3. `cos pr submit --task TASK-X` in process P2 → recomputes session=pid-<P2> ≠ pid-<P1> → `_branch_for`/worktree path point at a non-existent `TASK-X-pid-<P2>` → raises "no open worktree at … — run 'cos pr open' first"; the opened branch can never be submitted or cleaned up by a fresh process.

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** a worktree opened under session id A for TASK-X, **When** `cos pr submit --task TASK-X` runs under a different/absent session id, **Then** it resolves the real `agents/TASK-X/A` branch + its worktree from disk and submits it (no "no open worktree" error).
**Given** the session-derived worktree path exists (the common case), **When** submit/cleanup run, **Then** behavior is byte-identical (fast path, no disk scan).
**Given** two worktrees exist for the same task slug, **When** resolution runs, **Then** it falls back to the computed pair (no wrong-worktree guess).

## Work Log
- 2026-06-24 [claude]: Edit pr-workflow.md
- 2026-06-24 [claude]: Edit pr_commands.py
- 2026-06-24 [claude]: Edit pr_commands.py
- 2026-06-24 [claude]: Edit pr_commands.py
- 2026-06-24 [claude]: Edit test_cli.py
- 2026-06-24 [claude]: Fixed C3: added _resolve_worktree(repo, task_slug, session) — fast path on session-derived path, else single-match…
- 2026-06-24 [claude]: Verified by prior session, adopted this session: 2 targeted tests green + full test_cli.py matrix suite 195 passed…
