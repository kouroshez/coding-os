---
id: TASK-519
title: "Owner-independent orphan reaper: GC dead-agent worktrees/branches/PRs via presence-offline (SessionStart/cron)"
swimlane: core
kind: feature
epic: multi-agent-pr-mode
labels: [pr-mode, reaper, safety]
status: icebox
priority: P1
appetite: 1d
created: 2026-06-22
started: null
completed: null
agent_session: null
depends_on: [TASK-517]
blocked_by: []
references: []
---

# TASK-519: Owner-independent orphan reaper: GC dead-agent worktrees/branches/PRs via presence-offline (SessionStart/cron)

**Outcome (one sentence):** Cleanup becomes owner-independent so a crashed agent never leaves orphans (the exact failure mode behind Rule 21). A SessionStart/cron sweep keyed on board_os/presence.py "offline" reaps the worktree + local branch + remote branch + open PR of dead-session tasks; live worktrees are git-worktree-lock'd so a peer's prune cannot remove them; a pending-cleanup ledger (atomic record-verify pattern) drains offline/partial cleanups on the next online session; install-git-hooks runs once at enable so the .git-level second line of defense exists inside worktrees.

## Read First
- src/core/board_os/presence.py
- src/core/hooks/agent-presence.sh
- src/core/board_os/mcp_tools.py
- src/scripts/install-git-hooks.sh

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** a task whose owning session is presence-offline AND whose worktree/branch/PR still exist, **When** the reaper runs at SessionStart, **Then** the worktree is removed, local+remote branch deleted, and the PR closed, with each action logged. **Given** a live worktree of an active session, **When** a peer runs cleanup/prune, **Then** the live worktree is NOT removed (git worktree lock). **Given** tests for offline-detection + ledger-drain, **Then** green.

## Work Log
