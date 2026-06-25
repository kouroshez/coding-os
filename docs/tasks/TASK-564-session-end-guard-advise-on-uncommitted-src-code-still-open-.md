---
id: TASK-564
title: "session-end guard: advise on uncommitted src/** code + still-open bound task at end-of-turn (extend session-end.sh beyond docs/)"
swimlane: core
kind: feature
epic: null
labels: [hooks, reliability, forgot-step, audit-2026-06-24, ready]
status: complete
priority: P2
appetite: 1d
created: 2026-06-24
started: 2026-06-24
completed: 2026-06-24
agent_session: ses-claude-20260624-182639-f22b
depends_on: []
blocked_by: []
references: []
---
# TASK-564: session-end guard: advise on uncommitted src/** code + still-open bound task at end-of-turn (extend session-end.sh beyond docs/)

**Outcome (one sentence):** session-end.sh's Stop-time advisory also surfaces uncommitted NON-docs (src/**) code — not just uncommitted docs/ — staying ADVISORY (stderr) because a Stop hook cannot block an already-billed turn, and never auto-committing (which pollutes history on a trunk repo); this closes the empirically-recurring "left work uncommitted" forgot-step per the 2026 "hooks beat advisory memory" consensus.

## Scope correction (discovered during Orient — reuse-first / Rule 22)
- **Still-open bound task** (original bullet 2): ALREADY emitted by the live, registered sibling Stop hook `warn-abandoned-task.sh` (registry:698) — it queries `tasks WHERE status IN ('in_progress','testing') AND agent_session=SESSION_ID`, names each with the close command, debounced per session. Duplicating it in session-end.sh would double-nudge every turn → NOT added. The "reuse warn-abandoned-task.sh's query" requirement is satisfied by *leaving it there*, not copying it.
- **Unpushed-commits nudge**: deliberately NOT added. In trunk mode push is deferred to task-close by design, so unpushed commits are the normal mid-session state; a per-turn "N unpushed" line would be noise that contradicts the workflow.

## Read First
- src/core/hooks/session-end.sh
- src/core/hooks/warn-abandoned-task.sh
- src/core/hooks/session-context.sh

## Repro Steps
session-end.sh:108-117 counts only `git status --porcelain -- docs | grep -cE '\.md$'`; uncommitted src/** CODE at end-of-turn gets NO Stop advisory — only the NEXT SessionStart [Uncommitted Work] block catches it, so between a Stop and a crash the code is invisible.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** an agent ends a turn with uncommitted changes outside docs/ (src/**, tests/, …) **When** the Stop hook fires **Then** session-end.sh emits a one-line stderr advisory naming the change count + a `git status` hint, alongside the existing docs/ advisory
- **Given** the only uncommitted changes are board files under docs/tasks/ **When** the Stop hook fires **Then** the new code advisory does NOT fire (board churn is excluded via `:(exclude)docs`)
- **Then** the still-open-task nudge remains solely in warn-abandoned-task.sh (no duplication), the hook stays fail-open (exit 0), adds NO new file/schema/hook, and `make verify-hooks` passes

## Work Log
- 2026-06-25 [claude]: Edit session-end.sh
- 2026-06-25 [claude]: Edit test_hooks.py
- 2026-06-25 [claude]: Implemented ONLY the genuine gap: a non-docs uncommitted-code advisory via `git status --porcelain -- .…
- 2026-06-25 [claude]: commit 200791a29d — chore(board): sync TASK-563 lifecycle (complete + work-log) to disk
