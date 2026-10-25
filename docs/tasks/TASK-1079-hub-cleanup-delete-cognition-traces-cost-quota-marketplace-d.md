---
id: TASK-1079
title: "Hub cleanup: delete Cognition traces/cost/quota, Marketplace, Design and Search; move Roles into Config"
swimlane: core
kind: refactor
epic: null
labels: [docs-update, hub, ready]
status: in_progress
priority: P1
appetite: 1d
created: 2026-10-25
started: 2026-10-24
completed: null
agent_session: ses-claude-20261024-131905-031f
depends_on: []
blocked_by: []
references: []
---
# TASK-1079: Hub cleanup: delete Cognition traces/cost/quota, Marketplace, Design and Search; move Roles into Config

**Outcome (one sentence):** The Hub keeps only what an operator uses to see agent results (chat, board, memory, sessions, config with roles, graph, diagnostics); the Cognition page, trace views, dispatch cost/quota panels, the Search tab and the two coming-soon placeholders are gone from the SPA and their routes from the backend.

## Read First
- docs/engineering/hub-architecture.md
- src/core/web/routes/cognition.py
- src/core/web/ui/src/App.tsx

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the rebuilt SPA, **When** the operator opens any former Cognition, Marketplace, Design or Search URL, **Then** it redirects to a live page instead of rendering a removed one.
- **Given** the backend, **When** /openapi.json is read, **Then** no /api/cognition/trace*, /cost*, /dispatchers*, /analyze, /quota or /api/search/* path remains, while /api/cognition/chat*, /roles, /author-task and onboarding stay.
- **Given** Config, **When** the operator opens the Roles tab, **Then** the role roster and chain that lived under Cognition render there.
- **Given** the change, **When** the touched web/route test files and the UI build run, **Then** they pass and no remaining file imports a deleted module.

## Work Log
