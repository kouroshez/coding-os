---
id: TASK-1108
title: "feat(review): the reviewer gets the task's own diff and acceptance criteria and maps each to a test"
swimlane: "board_os"
kind: feature
epic: null
labels: [hooks, ready]
status: complete
priority: P1
appetite: 1d
created: 2026-11-24
started: 2026-11-24
completed: 2026-11-24
agent_session: ses-claude-20261123-135444-89e7
depends_on: []
blocked_by: []
references: []
---
# TASK-1108: feat(review): the reviewer gets the task's own diff and acceptance criteria and maps each to a test

**Outcome (one sentence):** Every commit made while a task is current is recorded against it, and the review receives that task's exact diff, title, outcome and acceptance criteria and reports any criterion no test covers, so parallel sessions' commits never enter another task's review.

## Read First
- docs/engineering/agent-supervision.md
- src/core/hooks/_helpers/auto_dispatch.py
- src/core/board_os/review_gate.py
- src/core/thinking_os/agents/reviewer.md
- src/core/hooks/registry.yaml

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a session commits while TASK-N is its current task, **When** the Bash git commit succeeds, even quietly with `-q`, **Then** link-commit-to-task.sh writes `commit <sha> — <subject>` into TASK-N's Work Log, and a recent commit whose subject is not in the command is never linked.
- **Given** TASK-N has recorded commits, **When** its review is dispatched, **Then** the reviewer input carries review_scope with those commits, their files and diff, plus the task title, outcome and acceptance criteria.
- **Given** another session committed on main while TASK-N ran, **When** TASK-N is reviewed, **Then** that commit is not in TASK-N's review_scope.
- **Given** the reviewer prompt, **When** a review runs, **Then** it tells the reviewer to name the covering test for every acceptance criterion and to report an uncovered one as a medium finding.

## Work Log
- 2026-11-24 [claude]: Deliberation: the reviewer received only the task id (build_input_slice's task_description is the marker), so it…
- 2026-11-24 [claude]: commit cafd25a092 — feat(review): the reviewer gets the task's own diff and acceptance criteria
- 2026-11-24 [claude]: commit 06198eea01 — fix(hooks): link commits to their task with cos's own Python
- 2026-11-24 [claude]: commit 4092e6e29b — fix(review): scope from the Work Log only, project root from the resolver, no generic-subject links
- 2026-11-24 [claude]: Status transitioned to complete via cos task-done.
- 2026-11-24 [claude]: Reused link-commit-to-task.sh instead of a new ledger: its quiet-commit fallback now matches by subject (≥12 chars),…
