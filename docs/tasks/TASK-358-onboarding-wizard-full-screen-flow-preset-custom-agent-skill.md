---
id: TASK-358
title: "Onboarding wizard \u2014 full-screen flow (preset/custom, agent, skills preview, optional name, description) + dry-run validation"
swimlane: core
kind: feature
epic: B-onboarding
labels: [wave-2, onboarding-program, ready]
status: complete
priority: P0
appetite: 3d
created: 2026-06-11
started: 2026-06-11
completed: 2026-06-11
agent_session: ses-claude-20260610-185418-2b3f
depends_on: [TASK-356, TASK-352]
blocked_by: []
references: []
---
# TASK-358: Onboarding wizard — full-screen flow (preset/custom, agent, skills preview, optional name, description) + dry-run validation

**Outcome (one sentence):** Clicking "New project" opens a step-wise onboarding flow: preset-or-custom, agent picker (removes hardcoded claude at hub.py:350), language/stack, live skill preview, extra skills, swimlane preview, optional project name ("don't know yet" temp slug + later rename), 1-2 paragraph description, review step; backed by POST /api/hub/registry/validate-init dry-run.

## Read First
- src/core/web/ui/src/pages/HubHome.tsx
- src/core/web/routes/hub.py
- src/core/web/ui/src/App.tsx
- src/core/web/routes/config.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the HubHome, **When** "New project" is clicked, **Then** the full-screen wizard renders all steps in order (preset/custom → agent → language-or-stack → skills preview → extra skills → swimlanes → name-or-skip → description → review) with back navigation preserving state.
- **Given** the agent step, **When** options load, **Then** they come from the adapters registry endpoint (claude/codex/cursor) and the chosen agent reaches the init subprocess — no hardcoded agent remains in hub.py.
- **Given** "don't know yet" on the name step, **When** the project is created, **Then** a generated temp slug is used and the project can be renamed later without breaking its registry entry.
- **Given** invalid input (bad name, unwritable parent, missing template), **When** validate-init dry-run is called at the review step, **Then** errors render inline before any subprocess starts.
- **Given** the UI build, **When** `make ui-build` and the web-route tests run, **Then** both green; wizard logic covered by component tests.

## Work Log
- 2026-06-11 [claude]: IMPL DONE (parked in testing per batch cadence) — full-screen OnboardingWizard.tsx (preset/custom → agent → skills previ
- 2026-06-11 [claude]: CLOSED on batched suite: test_cli.py 94 passed (14m09s) + hub routes 21/21 + wizard component 7/7 + pages 26/26 + ui-bui
