---
id: TASK-270
title: "DoR gate warns when Read First references paths that don't exist"
swimlane: core
kind: feature
epic: hub-redesign
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-06-08
started: 2026-06-08
completed: 2026-06-08
agent_session: ses-claude-618-2ab7
depends_on: []
blocked_by: []
references: []
---
# TASK-270: DoR gate warns when Read First references paths that don't exist

**Outcome (one sentence):** Starting a task whose Read First lists repo paths that don't exist surfaces a warning naming the dead paths, so a bogus/incomplete Read First is caught before it misleads the implementer — without blocking legitimate non-file references.

## Read First
- src/core/board_os/transition_gates_validator.py — _evaluate_section (~92), evaluate_dor (~205)
- src/core/board_os/transition-gates.yaml — Read First rule (min_items)
- src/core/board_os/tests/test_mcp_tools.py — transition/gate tests

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a task whose Read First bullets reference repo paths (e.g. src/…, docs/…) that do not exist, **When** the DoR gate evaluates it, **Then** it adds a WARN (DOR_READ_FIRST_DEAD_LINK) naming the missing paths — not a BLOCK.
- **Given** a Read First that references only existing paths or non-path prose (URLs, "the running hub"), **When** the gate evaluates it, **Then** no dead-link warning is raised.
- **Given** a Read First bullet with a glob, anchor (#L42), or :line suffix, **When** checked, **Then** the suffix/glob is normalised away and only the real file is stat'd.

## Work Log
- 2026-06-08 [claude]: DoR gate gained a Read First dead-link check: _read_first_missing_paths stats repo-path-shaped bullets (markdown link ta
