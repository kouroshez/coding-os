---
id: TASK-535
title: "pr reaper destroys uncommitted/unpushed work \u2014 preserve (bundle) before GC in _reap_one"
swimlane: infra
kind: bug
epic: pr-mode-p0-hardening
labels: [pr-mode, data-loss, reaper, critical, ready]
status: testing
priority: P0
appetite: 1d
created: 2026-06-24
started: 2026-06-24
completed: null
agent_session: ses-claude-20260623-225054-17eb
depends_on: []
blocked_by: []
references: []
---
# TASK-535: pr reaper destroys uncommitted/unpushed work — preserve (bundle) before GC in _reap_one

**Outcome (one sentence):** _reap_one never destroys work that is not already on origin or captured in a durable recovery bundle; the worktree (a disposable checkout) is still GC'd. Closes the #1 confirmed data-loss risk that TASK-526/530 hardened the reap TRIGGER for but left the DESTROY unsafe.

## Read First
- src/cli/pr_commands.py
- docs/playbooks/pr-workflow.md
- src/core/hooks/pr-reap.sh

## Repro Steps
_reap_one (src/cli/pr_commands.py:771-790) calls `git worktree remove --force` + `git branch -D` unconditionally — no `git status --porcelain` (uncommitted) or `_branch_recoverable` (unpushed) check, unlike cleanup (line 591-614). A crashed agent (dead pid → _session_state=='offline') with unpushed/uncommitted work is permanently destroyed by the unsupervised SessionStart reaper.

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** an offline orphan worktree with a local-only commit and/or uncommitted changes, **When** `cos pr reap` runs, **Then** a git bundle capturing the branch tip + stash is written under ~/.coding-os/reaped/<slug>/ and the worktree is removed; the branch is deleted ONLY after the bundle is confirmed OR it is recoverable from origin/integration. **And** a clean, origin-recoverable orphan still GCs branch+worktree+remote+PR exactly as before (no regression). Verified by `uv run pytest tests/test_cli.py -q`.

## Work Log
- 2026-06-24 [claude]: Edit pr-workflow.md
- 2026-06-24 [claude]: Edit test_observability_smoke.py
- 2026-06-24 [claude]: Edit pr_commands.py
- 2026-06-24 [claude]: Edit pr_commands.py
- 2026-06-24 [claude]: Edit pr_commands.py
- 2026-06-24 [claude]: Edit pr_commands.py
- 2026-06-24 [claude]: Edit test_cli.py
- 2026-06-24 [claude]: Chose preserve-before-GC (WIP-commit add -A --no-verify → git bundle to ~/.coding-os/reaped, COS_REAPED_ROOT…
