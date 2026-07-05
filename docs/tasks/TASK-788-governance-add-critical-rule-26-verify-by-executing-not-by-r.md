---
id: TASK-788
title: "governance: add Critical Rule 26 \u2014 verify by executing, not by reading (run the deliverable before claiming done)"
swimlane: docs
kind: docs
epic: null
labels: [ready]
status: complete
priority: P1
appetite: 1d
created: 2026-07-05
started: 2026-07-04
completed: 2026-07-04
agent_session: ses-claude-20260704-201536-1b8d
depends_on: []
blocked_by: []
references: []
---
# TASK-788: governance: add Critical Rule 26 — verify by executing, not by reading (run the deliverable before claiming done)

**Outcome (one sentence):** A new Critical Rule 26 codifies the doctrine that generalizes api-contract-discipline from data contracts to runtime/behaviour contracts: never claim a deliverable works or hand the user a command/behaviour you did not execute this session; reading code (a CLI flag, an import path) is not verification, and a green proxy suite (pytest) does not prove the delivered executable runs. Landed as: Rule 26 section + index row in docs/governance/critical-rules.md, index row in AGENTS.md, an operational body section in src/core/rules/test-discipline.md, and a cross-link from src/core/rules/api-contract-discipline.md. make docs-lint green.

## Read First
- docs/governance/critical-rules.md
- AGENTS.md
- src/core/rules/test-discipline.md
- src/core/rules/api-contract-discipline.md

## Work Log
- 2026-07-05 [claude]: Edit test-discipline.md
- 2026-07-05 [claude]: Edit api-contract-discipline.md
- 2026-07-05 [claude]: Edit critical-rules.md
- 2026-07-05 [claude]: Edit critical-rules.md
- 2026-07-05 [claude]: Edit AGENTS.md
- 2026-07-05 [claude]: Rule 26 landed (153b5ec7): critical-rules.md §Rule26 + index row, AGENTS.md index row, test-discipline.md §"Run the…
