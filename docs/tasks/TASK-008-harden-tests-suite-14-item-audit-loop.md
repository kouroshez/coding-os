---
id: TASK-008
title: "Harden tests/ suite — 14-item audit loop"
swimlane: infra
kind: chore
epic: null
labels: [tests, quality]
status: complete
priority: P2
appetite: "1d"
created: 2026-05-21
started: 2026-05-21
completed: 2026-05-22
agent_session: ses-claude-20260522-1151
depends_on: []
blocked_by: []
references: []
---
# TASK-008: Harden tests/ suite — 14-item audit loop

**Outcome (one sentence):** The `tests/` suite is green, fast, and
standard — no failing tests, slow tests marked, shared fixtures, and the
brittle/vacuous-assertion patterns from the audit removed.

## Read First
- docs/governance/critical-rules.md — Rule 11 (no hardcoded stack/adapter
  literals), Rule 20 (test discipline), Rule 13 (MCP envelope).
- src/core/rules/test-discipline.md — matrix-targeted verification.
- src/core/rules/api-contract-discipline.md — producer-verified field names.

## Acceptance (G/W/T)
- **Given** the `tests/` suite.
- **When** `pytest tests/` runs.
- **Then** 0 failures (excluding tests blocked on the user's in-flight WIP),
  slow files carry `@pytest.mark.slow`, and the audit checklist items L1–L14
  are each committed with a 10/10 self-score.

## Work Log
- L1a–L1e + composer fix: ~30 baseline reds resolved. See audit Evidence Log.
- 2026-05-22 [claude]: Closed: status→complete, 14 category rows resolved (11 done, 3 deferred per Rule 22 — L5/
