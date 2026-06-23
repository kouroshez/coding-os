---
id: TASK-519
title: "Owner-independent orphan reaper: GC dead-agent worktrees/branches/PRs via presence-offline (SessionStart/cron)"
swimlane: core
kind: feature
epic: multi-agent-pr-mode
labels: [pr-mode, reaper, safety, ready]
status: complete
priority: P1
appetite: 1d
created: 2026-06-22
started: 2026-06-23
completed: 2026-06-23
agent_session: ses-claude-20260622-134704-4de9
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
- 2026-06-23 [claude]: Edit pr_commands.py
- 2026-06-23 [claude]: Edit pr_commands.py
- 2026-06-23 [claude]: Edit pr_commands.py
- 2026-06-23 [claude]: Edit pr-reap.sh
- 2026-06-23 [claude]: Edit registry.yaml
- 2026-06-23 [claude]: Edit subsystems.yaml
- 2026-06-23 [claude]: Edit adapter.yaml
- 2026-06-23 [claude]: Edit adapter.yaml
- 2026-06-23 [claude]: Edit test_cli.py
- 2026-06-23 [claude]: Edit pr_commands.py
- 2026-06-23 [claude]: commit 800db8caa0 — feat(pr-mode): owner-independent orphan reaper (cos pr reap + SessionStart hook)
- 2026-06-23 [claude]: Edit codex-sessionstart-dispatch.sh
- 2026-06-23 [claude]: commit 59f10973d1 — fix(codex): add pr-reap.sh to the SessionStart dispatch loop (parity)
- 2026-06-23 [claude]: cos pr reap (pr_commands.py): scans worktrees, reaps presence-offline sessions (worktree+local/remote branch+PR via…
