---
id: TASK-617
title: "Reaper: hoist the per-candidate git worktree list to one call (O(K\u00b7N) to O(N)) and add a cross-host liveness simulation test"
swimlane: core
kind: bug
epic: git-foundation-hardening
labels: [pr-mode, reaper, performance, ready]
status: archive
priority: P2
appetite: 1d
created: 2026-06-27
started: 2026-06-27
completed: 2026-06-27
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-617: Reaper: hoist the per-candidate git worktree list to one call (O(K·N) to O(N)) and add a cross-host liveness simulation test

**Outcome (one sentence):** pr_reap calls _lock_owner_alive (→ `git worktree list --porcelain`, a FULL-list subprocess) once PER unknown+stale candidate, plus a `rev-parse` per worktree — O(K·N) forks per sweep on a path backgrounded on every SessionStart. Hoist a single porcelain dump before the loop (the block already carries branch + locked reason) so the sweep is O(N); and add the missing cross-host liveness simulation test (a presence/lock-reason owner on a FOREIGN host) asserting a foreign-host pid is never treated as locally-alive proof and the worktree is reaped (work preserved first) — the reaper currently has no cross-host coverage.

## Read First
- src/cli/pr_commands.py
- src/core/board_os/presence.py
- tests/test_cli.py

## Repro Steps
Workflow whdjyvqjq + the prior /code-review (CONFIRMED): _worktree_lock_reason runs `git worktree list --porcelain` inside _lock_owner_alive, called per-candidate in pr_reap's loop; _agent_worktrees already shows the single-pass porcelain pattern to reuse. Cross-host: _lock_owner_alive is host-local (pid_alive) but no test simulates a foreign host.

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** a reap sweep over K unknown+stale candidates among N worktrees, **When** it runs, **Then** `git worktree list` is invoked ONCE (not once per candidate) and behavior is unchanged. **Given** a worktree whose owner pid is stamped on a FOREIGN host, **When** the reaper sweeps and the tree is age-stale, **Then** it is reaped (work bundle-preserved first), not kept as falsely-alive. **Given** a same-host live owner, **Then** it is still kept. Verify: `uv run pytest tests/test_cli.py::TestCosPr -q` with a fork-count assertion + a cross-host sim case.

## Work Log
- 2026-06-28 [claude]: Added _worktree_index (one porcelain dump → {path:{branch,locked}}) so the sweep reads both branch and lock reason…
