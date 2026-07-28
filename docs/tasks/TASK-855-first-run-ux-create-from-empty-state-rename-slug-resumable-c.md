---
id: TASK-855
title: "First-run UX \u2014 create-from-empty-state, rename slug, resumable create job"
swimlane: core
kind: feature
epic: null
labels: [hub, onboarding, first-run, ready]
status: icebox
priority: P1
appetite: 1d
created: 2026-07-28
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-855: First-run UX — create-from-empty-state, rename slug, resumable create job

**Outcome (one sentence):** A user with zero projects can create one from the panel without touching the CLI, rename a temp slug, and survive a page reload mid-create.

## Read First
- docs/engineering/hub-architecture.md
- src/core/web/ui/src/pages/HubHome.tsx
- src/core/web/routes/hub.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** zero registered projects, **When** the hub home renders, **Then** the empty state offers "Create a project" as its primary call to action.
- **Given** a project registered under an auto-generated temp slug, **When** the user opens its actions menu, **Then** a rename control calls `PATCH /api/hub/registry/{slug}`.
- **Given** a create job in flight, **When** the page is reloaded, **Then** the wizard re-attaches to the running job through the snapshot endpoint instead of losing it.
- **Given** the import dialog, **When** it renders, **Then** its copy no longer claims panel scaffolding is a follow-up.

## Work Log
