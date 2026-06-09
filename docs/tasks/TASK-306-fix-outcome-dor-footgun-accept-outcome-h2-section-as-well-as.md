---
id: TASK-306
title: "Fix Outcome DOR footgun: scope extraction to the H2 Outcome section, not a blind whole-body regex"
swimlane: core
kind: bug
epic: panel-state-isolation
labels: [board, dx, parser, ready]
status: testing
priority: P2
appetite: 1d
created: 2026-06-09
started: 2026-06-09
completed: null
agent_session: ses-claude-20260609-163314-6565
depends_on: []
blocked_by: []
references: []
---
# TASK-306: Fix Outcome DOR footgun: scope extraction to the H2 Outcome section, not a blind whole-body regex

## Outcome

**Outcome (one sentence):** Make the Outcome DOR check read the dedicated H2 Outcome section as its primary source and accept a plain H2 form in addition to the inline bold marker, so a freeform body edit no longer blocks the transition with a misleading missing-or-short Outcome error.

## Repro Steps

1. Create a task, then set its body via a freeform edit that writes the outcome under a normal H2 heading (every other required section is an H2).
2. Run the transition / validate.
3. Observe a misleading DOR_OUTCOME_MISSING (no inline bold marker) or DOR_OUTCOME_TOO_SHORT (the blind regex latched onto a different bold token in the prose).

## Read First

- src/core/board_os/parser.py
- src/core/board_os/transition_gates_validator.py

## Acceptance

**Given** a task whose Outcome is a plain H2 section (no inline bold marker), or whose prose mentions a bold token,
**When** the Outcome is extracted for the DOR gate,
**Then** the section's own text is returned (section-scoped, not a blind whole-body search) and the gate passes — while the existing inline bold-marker form keeps working, both proven by unit tests.
