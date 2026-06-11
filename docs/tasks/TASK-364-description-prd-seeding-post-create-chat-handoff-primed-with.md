---
id: TASK-364
title: "Description\u2192PRD seeding + post-create chat handoff primed with project context"
swimlane: core
kind: feature
epic: B-onboarding
labels: [wave-2, onboarding-program, ready]
status: testing
priority: P1
appetite: 2d
created: 2026-06-11
started: 2026-06-11
completed: null
agent_session: ses-claude-20260610-185418-2b3f
depends_on: [TASK-358]
blocked_by: []
references: []
---
# TASK-364: Description→PRD seeding + post-create chat handoff primed with project context

**Outcome (one sentence):** The onboarding description feeds PROJECT_DESCRIPTION substitution and (when docs module is on) auto-seeds docs/prd via the cos setup pipeline with a no-LLM degrade path; after create, the user lands in workspace chat with the agent primed with the project description.

## Read First
- src/cli/setup.py
- src/templates/_base/base.yaml
- src/core/web/routes/cognition.py
- src/core/web/ui/src/pages/ChatLanding.tsx

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a description entered in the wizard (or --summary in CLI), **When** init scaffolds, **Then** PROJECT_DESCRIPTION placeholders across scaffold docs render the user text (not the generic default) — fixture test on at least vision + index docs.
- **Given** docs module on, **When** the docs-seed phase runs, **Then** docs/prd snapshot-vision is seeded from the description via the setup pipeline; with no LLM available the verbatim-description degrade path still produces valid docs (both paths tested).
- **Given** create completes, **When** the user lands in /p/{slug}/workspace/chat, **Then** the first agent context contains the project description (primed handoff) and a smoke test asserts the priming payload.
- **Given** the matrix, **When** `uv run pytest tests/test_cli.py -q` + web-route tests run, **Then** green.

## Work Log
