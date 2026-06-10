---
id: TASK-318
title: "Hub chat Auto model option \u2014 orchestrator model triages via cos_route_model when model_routing.enabled"
swimlane: core
kind: feature
epic: null
labels: [model-routing, hub-ui, audit-2026-06-09, ready]
status: icebox
priority: P2
appetite: 1d
created: 2026-06-10
started: null
completed: null
agent_session: null
depends_on: [TASK-317, TASK-308]
blocked_by: []
references: []
---

# TASK-318: Hub chat Auto model option — orchestrator model triages via cos_route_model when model_routing.enabled

**Outcome (one sentence):** When model_routing.enabled, the hub chat model picker offers "Auto": selecting it boots the configured orchestrator_model first, which classifies the prompt (cos_classify_prompt + cos_route_model) and hands the session to the chosen model; toggle off = the Auto option is absent entirely.

## Read First
- src/core/web/ui/src/pages/ChatLanding.tsx (model picker)
- src/core/web/routes/cognition.py (chat session boot)
- src/core/thinking_os/tools/routing.py (cos_route_model contract)
- src/adapters/claude/sdk_dispatcher.py (model forwarded to sub-session)
- docs/tasks pointer: TASK-317 (settings SSOT this consumes)

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** model_routing.enabled=false
- **When** the chat model picker renders
- **Then** no "Auto" entry exists (feature invisible)
- **Given** enabled=true and picker set to Auto
- **When** the user sends the first message
- **Then** the orchestrator_model from settings runs first, records a routing decision (cos_route_model), and the session continues on the routed model — both models visible in the session trace
- **Given** the API contract discipline rule
- **When** the UI consumes the routing response
- **Then** field names verified against the producer route (no source/source_uid-class drift), with a UI-level test

## Work Log
