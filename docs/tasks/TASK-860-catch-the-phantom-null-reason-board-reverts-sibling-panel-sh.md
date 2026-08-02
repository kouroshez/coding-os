---
id: TASK-860
title: "Catch the phantom NULL-reason board reverts (sibling panel shares session id)"
swimlane: "board_os"
kind: bug
epic: null
labels: [lifecycle, drift, concurrency, ready]
status: icebox
priority: P2
appetite: 1d
created: 2026-08-02
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-860: Catch the phantom NULL-reason board reverts (sibling panel shares session id)

**Outcome (one sentence):** The writer of unattributed in_progress→icebox reverts is identified and prevented: two panels can no longer share one session id (or the sharing is made safe), and every backward move carries an honest actor + reason.

## Read First
- src/core/board_os/_agent_runtime.py
- src/core/hooks/session-context.sh
- src/core/hooks/nudge-reentry.sh
- src/core/hooks/warn-abandoned-task.sh
- docs/engineering/state-files.md

## Repro Steps
2026-08-02: TASK-859 (17:25:37) and TASK-829 (17:48:57) were each reverted in_progress→icebox 30s–7min after being started, reason=NULL, agent_session=ses-claude-20260527-151803-0b9f. Live hub metrics show ZERO board.move/reposition requests (hub exonerated); sync_one always writes a reason (sync exonerated); tests are tmp-isolated. Two panels carry the SAME session id: 86ed2039 (active worker) and beea135e (created 16:57:41, task_current=none) — the idle sibling receiving nudge-reentry/warn-abandoned prompts about cards it "owns" is the prime suspect. transparency-banner.md promises "the ses= tail differs per tab"; here it does not.

## Acceptance (G/W/T) — *this IS the Definition of Done*
1. **Given** the repro evidence below, **When** the investigation completes, **Then** the exact caller of the NULL-reason in_progress→icebox moves is named with a captured stack/log line, not inferred.
2. **Given** a resumed/duplicated conversation opened in a second panel, **When** both panels are live, **Then** they do not share one session id (or board mutations from the idle one are refused/attributed distinctly).
3. **Given** any backward status move, **When** it is recorded, **Then** task_status_history carries a non-empty reason or a synthesized source tag.

## Work Log
