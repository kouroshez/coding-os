---
id: TASK-531
title: "cos-env worktree detection fails for custom COS_WORKTREE_ROOT + litters a stray .coding-os into the worktree"
swimlane: core
kind: bug
epic: pr-mode-hardening
labels: [pr-mode, state-routing, worktree, ready]
status: archive
priority: P2
appetite: 1d
created: 2026-06-23
started: 2026-06-23
completed: 2026-06-23
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-531: cos-env worktree detection fails for custom COS_WORKTREE_ROOT + litters a stray .coding-os into the worktree

**Outcome (one sentence):** Worktree detection + state routing is git-native (compare git rev-parse --git-common-dir parent vs --show-toplevel) so it works regardless of where the worktree lives, including a custom COS_WORKTREE_ROOT that fresh hook subprocesses never inherit; on an unresolvable/degraded route cos-env never falls back to a RELATIVE .coding-os and never writes a heartbeat under the worktree cwd (no stray .coding-os polluting the agent's own PR); the pr-workflow.md COS_PROJECT_ROOT 'export' wording is corrected to describe the git-native mechanism.

## Read First
- src/core/hooks/cos-env.sh
- src/cli/pr_commands.py
- docs/playbooks/pr-workflow.md

## Repro Steps
export COS_WORKTREE_ROOT=/tmp/wt; cos pr open creates /tmp/wt/<slug>; in a fresh shell (COS_WORKTREE_ROOT unset) cd into it and source cos-env.sh → COS_STATE_DIR resolves to a relative ./.coding-os and a heartbeat is written inside the worktree.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a custom COS_WORKTREE_ROOT not under ~/.coding-os/worktrees and an unset env in a fresh hook **When** cos-env is sourced from inside that worktree **Then** state routes to the MAIN repo's .coding-os (git-native), not a relative cwd dir.
- **Given** an unresolvable git layout **When** cos-env degrades **Then** it writes NO panel dir/heartbeat under the worktree (no stray .coding-os) and surfaces a loud misroute.
- **And** `make verify-hooks` + `uv run pytest tests/test_cli.py -q` are green.

## Work Log
- 2026-06-24 [claude]: Deliberation: make worktree detection git-native — add a fallback that fires only when BOTH dispatch fast-paths…
- 2026-06-24 [claude]: Edit pr-workflow.md
- 2026-06-24 [claude]: Edit cos-env.sh
- 2026-06-24 [claude]: Edit cos-env.sh
- 2026-06-24 [claude]: Edit test_hooks.py
- 2026-06-24 [claude]: Edit cos-env.sh
- 2026-06-24 [claude]: Edit cos-env.sh
- 2026-06-24 [claude]: Edit comments-terse-why-only.md
- 2026-06-24 [claude]: Edit MEMORY.md
- 2026-06-24 [claude]: commit 1f8869b501 — fix(pr-mode): git-native worktree detection in cos-env — no stray .coding-os in the PR
- 2026-06-24 [claude]: Status transitioned to complete via cos task-done.
