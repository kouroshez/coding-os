---
id: TASK-994
title: "governance: the verification matrix omits the file-size gate that CI enforces"
swimlane: infra
kind: bug
epic: null
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-08-15
started: 2026-08-15
completed: 2026-08-15
agent_session: ses-claude-20260814-120316-413b
depends_on: []
blocked_by: []
references: []
---
# TASK-994: governance: the verification matrix omits the file-size gate that CI enforces

**Outcome (one sentence):** The matrix row for an added or edited .py names every gate CI runs on it, so a change that satisfies the row cannot still fail CI on file size.

## Read First
- AGENTS.md
- tests/test_file_size_budget.py
- src/core/rules/anti-overengineering.md

## Repro Steps
Adding three tests pushed tests/test_hooks_gates.py to 523 lines. `make lint` — the only command in the matrix row for an edited .py — passed, and CI then failed on tests/test_file_size_budget.py across all three Python versions. `make check-file-size` is not the fix: it exits 1 on a clean tree today, warning on 89 pre-existing files past 400 lines.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a .py edit that pushes a file past 500 lines, **When** the agent runs the matrix row for that change, **Then** the failure surfaces locally instead of in CI.
- **Given** the added command, **When** it runs on a clean tree, **Then** it passes — so the row is not permanently red.

## Work Log
- 2026-08-15 [claude]: Edit AGENTS.md
- 2026-08-15 [claude]: Added the file-size gate to the matrix row rather than make check-file-size: that target exits 1 on a clean tree…
- 2026-08-15 [claude]: Status transitioned to complete via cos task-done.
