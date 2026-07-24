---
id: TASK-526
title: "pr-mode reaper destroys a live agent's worktree \u2014 gate reap on PID-death/ended_at, not the 30-min idle pill"
swimlane: infra
kind: bug
epic: pr-mode-hardening
labels: [pr-mode, data-loss, reaper, critical, ready]
status: archive
priority: P0
appetite: 1d
created: 2026-06-23
started: 2026-06-23
completed: 2026-06-23
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-526: pr-mode reaper destroys a live agent's worktree — gate reap on PID-death/ended_at, not the 30-min idle pill

**Outcome (one sentence):** The owner-independent reaper never force-removes a worktree whose owning agent is still alive — session_presence 'offline' (a 30-min UI idle pill) is no longer treated as proof of death; reap requires ended_at set OR pid_alive(pid)==False; the dba50360 age-fallback no longer keys on top-level dir mtime (blind to src/** edits) but on a real-activity signal (git index mtime / recursive max-mtime) or is dropped for PID-liveness.

## Read First
- src/cli/pr_commands.py
- src/core/hooks/_helpers/presence_write.py
- docs/playbooks/pr-workflow.md

## Repro Steps
COS_GIT_WORKFLOW=pr; create an agents/x/<session> worktree; write a presence record with pid=alive and last_tool_at=now-31min; run `cos pr reap` → worktree force-removed (data loss). Also: edit only wt/src/deep/f.py (top-level dir mtime unchanged) with no presence record → reaped after 24h.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a PID-alive agent idle >30min mid-build **When** `cos pr reap` runs **Then** its worktree is KEPT (new test asserts kept).
- **Given** a no-record orphan that edited only src/** for >24h **When** reap runs **Then** it is KEPT (subdir-activity test).
- **Given** a session with ended_at set OR a dead PID **When** reap runs **Then** it IS reaped.
- **And** `uv run pytest tests/test_cli.py -q` + `tests/test_presence_classifier_parity.py` are green.

## Work Log
- 2026-06-23 [claude]: Edit pr-workflow.md
- 2026-06-23 [claude]: Edit pr_commands.py
- 2026-06-23 [claude]: Edit pr_commands.py
- 2026-06-23 [claude]: Edit pr_commands.py
- 2026-06-23 [claude]: Edit test_cli.py
- 2026-06-23 [claude]: Edit test_cli.py
- 2026-06-23 [claude]: Reaper death-oracle = ended_at|pid-dead (was session_presence offline idle-pill, finding D5-1); _worktree_stale now…
- 2026-06-23 [claude]: commit f8e2e1c18d — fix(pr-mode): reaper gates reap on PID-death/ended_at, not the idle pill; newest-mtime age-fallback
