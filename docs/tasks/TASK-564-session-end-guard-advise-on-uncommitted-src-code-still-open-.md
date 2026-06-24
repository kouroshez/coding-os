---
id: TASK-564
title: "session-end guard: advise on uncommitted src/** code + still-open bound task at end-of-turn (extend session-end.sh beyond docs/)"
swimlane: core
kind: feature
epic: null
labels: [hooks, reliability, forgot-step, audit-2026-06-24]
status: icebox
priority: P2
appetite: 1d
created: 2026-06-24
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-564: session-end guard: advise on uncommitted src/** code + still-open bound task at end-of-turn (extend session-end.sh beyond docs/)

---
id: TASK-564
title: "session-end guard: advise on uncommitted src/** code + still-open bound task at end-of-turn (extend session-end.sh beyond docs/)"
swimlane: core
kind: feature
epic: null
labels: [hooks, reliability, forgot-step, audit-2026-06-24]
status: icebox
priority: P2
appetite: 1d
created: 2026-06-24
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-564: session-end guard — advise on uncommitted src/** code + still-open bound task at end-of-turn

**Outcome (one sentence):** session-end.sh's Stop-time advisory also surfaces uncommitted NON-docs (src/**) changes AND a still-open bound in_progress/testing task — not just uncommitted docs/ — reusing warn-abandoned-task.sh's open-task query, staying ADVISORY (stderr / Stop additionalContext) because a Stop hook cannot block an already-billed turn, and never auto-committing (which pollutes history on a trunk repo); this closes the empirically-recurring "left work uncommitted / left a task open" forgot-step the Agent Digest shows as a recurring belief, per the 2026 "hooks beat advisory memory" consensus.

## Read First
- src/core/hooks/session-end.sh
- src/core/hooks/warn-abandoned-task.sh
- src/core/hooks/session-context.sh

## Repro Steps
session-end.sh:108-117 counts only `git status --porcelain -- docs | grep -cE '\.md$'`; uncommitted src/** CODE at end-of-turn gets NO Stop advisory — only the NEXT SessionStart [Uncommitted Work] block (session-context.sh:284-291) catches it, so between a Stop and a crash the code is invisible. The once-per-session warn-abandoned-task.sh nudge is fail-open and the Agent Digest "left a task open" is a recurring belief → nudge-not-enforce is empirically insufficient. There is also no "forgot to push" detector anywhere (grep-confirmed).

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** an agent ends a turn with uncommitted changes under src/** (code, not just docs) **When** the Stop hook fires **Then** session-end.sh emits a one-line advisory naming the file count + a `git status` hint (alongside the existing docs/ advisory), optionally noting unpushed commits in the same line
- **When** a task is still in_progress/testing bound to this session at turn-end **Then** the advisory also names it with the move/close command, reusing warn-abandoned-task.sh's query with no new state file
- **Then** the hook stays fail-open (always exit 0), adds NO new file/schema/hook, and `make verify-hooks` passes

## Work Log
