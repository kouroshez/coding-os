---
id: TASK-561
title: "pr-mode: cos pr cleanup must preserve before destroy \u2014 drifted-session cleanup can delete a live peer's uncommitted work"
swimlane: core
kind: bug
epic: multi-agent-pr-mode
labels: [pr-mode, data-loss, reaper, audit-2026-06-24]
status: icebox
priority: P1
appetite: 1d
created: 2026-06-24
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-561: pr-mode: cos pr cleanup must preserve before destroy — drifted-session cleanup can delete a live peer's uncommitted work

**Outcome (one sentence):** cos pr cleanup never destroys a LIVE peer's worktree/uncommitted work under session-id drift. Preferred fix: the peer-protection gate (pr_commands.py:842) also refuses when _session_state is 'unknown' AND owner_session != session ("can't prove the owner is dead → don't touch a peer"); equivalently/additionally cleanup runs _preserve_reaped (git bundle) before `worktree remove --force`, mirroring the reaper hardening (TASK-535) that cleanup never received.

## Read First
- src/cli/pr_commands.py
- docs/playbooks/pr-workflow.md
- docs/architecture/adr/0013-pr-mode-multi-agent-git-workflow-consumer-only.md

## Repro Steps
Audit probe probe_cleanup_peer.py reproduced end-to-end: peer-gate fires=False, pr_state=unknown, recoverable=True → cleanup removes the peer worktree with `worktree remove --force` + `branch -D` and NO _preserve_reaped → peer uncommitted work LOST. Code: pr_commands.py:296-304 (_resolve_worktree single-candidate), 842 (peer gate keyed on _session_state=='live'), 865 (_branch_recoverable merge-gate passes once on origin), 877-879 (destroy). Reaper (_reap_one) is data-loss-safe; cleanup is the gap.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a drifted session whose _resolve_worktree single-candidate fallback resolves a live peer's worktree and that peer has no 'live' presence record (so _session_state=='unknown' and its committed work is already on origin, recoverable=True)
- **When** `cos pr cleanup` runs without --force
- **Then** it refuses (or git-bundle-preserves first) so the peer's UNCOMMITTED file survives, while the normal own-worktree merged-PR cleanup path still cleans up as before

## Work Log
