---
id: TASK-247
title: "Onboarding: readiness endpoint + hero card on chat landing"
swimlane: core
kind: feature
epic: hub-redesign
labels: [ready]
status: complete
priority: P1
appetite: 1d
created: 2026-06-08
started: 2026-06-08
completed: 2026-06-08
agent_session: ses-claude-20260608-024900-f2b0
depends_on: []
blocked_by: []
references: []
---
# TASK-247: Onboarding: readiness endpoint + hero card on chat landing

**Outcome (one sentence):** Surface onboarding state and a hero CTA on the chat landing when product docs are still placeholders.

## Read First
- src/cli/main.py — `_run_scaffold_phase` (~1126) + `_initial_doc_index` (~1309): what cos init scaffolds (placeholder PRD).
- src/core/web/ui/src/pages/ChatLanding.tsx — where the OnboardingCard hero mounts.
- src/templates/_base/scaffold/docs/prd/01-snapshot-vision.md — the placeholder/_TODO markers.

## Context / Approach
Add GET /api/.../onboarding-status reading .coding-os/onboarding.json (written by the onboarder on completion), falling back to a placeholder-_TODO scan. Render an OnboardingCard hero on ChatLanding when onboarding is incomplete; dismissible, reappears collapsed until docs are authored. Depends on TASK-246.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a project with placeholder PRD, **When** the chat landing loads, **Then** a Set-up hero shows.
- **Given** .coding-os/onboarding.json is present, **When** the landing loads, **Then** the hero is hidden.

## Work Log
- 2026-06-08 [claude]: Added GET /api/cognition/onboarding-status (placeholder-_TODO scan + onboarding.json override) and OnboardingCard hero o
