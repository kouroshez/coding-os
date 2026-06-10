---
id: TASK-318
title: "Hub chat Auto model option \u2014 orchestrator model triages via cos_route_model when model_routing.enabled"
swimlane: core
kind: feature
epic: null
labels: [model-routing, hub-ui, audit-2026-06-09, ready]
status: complete
priority: P2
appetite: 1d
created: 2026-06-10
started: 2026-06-10
completed: 2026-06-10
agent_session: ses-claude-20260527-151803-0b9f
depends_on: [TASK-317, TASK-308]
blocked_by: []
references: []
---
# TASK-318: Hub chat Auto model option — orchestrator model triages via cos_route_model when model_routing.enabled

**Outcome (one sentence):** When model_routing.enabled, the hub chat model picker offers "Auto": the kernel's deterministic router (cos_classify_prompt heuristic × cos_route_model empirical history) picks the session model per prompt, falling back to the settings' orchestrator_model on cold start; toggle off = Auto absent and behaviour unchanged.

**Design note (refined during implementation):** an LLM orchestrator turn just to pick a model contradicts the repo's token-economy doctrine — cos_classify_prompt is deliberately "sub-second; deterministic; no LLM call". Auto therefore routes server-side at session boot: classify(prompt) → route_model(complexity); empirical recommendation wins when data_points>0, else the configurable orchestrator_model runs the session. The routing decision is emitted as a dedicated SSE event + trace record so the choice is always visible/auditable.

## Read First
- src/core/web/routes/cognition.py (chat_new — model handling ~L846)
- src/core/web/routes/settings.py (model_routing section — TASK-317)
- src/core/web/ui/src/features/cognition/ModelPicker.tsx
- src/core/thinking_os/tools/routing.py (route_model contract)
- docs/engineering/hub-architecture.md § Hub settings contract

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** model_routing.enabled=false
- **When** the chat model picker renders
- **Then** no "Auto" entry exists and model="auto" posted to /api/cognition/chat fails validation
- **Given** enabled=true, picker on Auto, and real routing history (data_points>0)
- **When** the user sends the first message
- **Then** the session boots on cos_route_model's recommendation and the SSE stream carries a routing event {complexity, model, source:"empirical"}
- **Given** enabled=true with cold routing history
- **When** the session boots
- **Then** the settings' orchestrator_model runs the session and the routing event says source:"orchestrator_default"
- **Given** the producer/consumer contract
- **When** the UI consumes settings + adapters
- **Then** field names verified against the emit sites, with route tests covering all three scenarios

## Work Log
- 2026-06-10 [claude]: Shipped (score 9/10). Design refined: deterministic server-side triage instead of an LLM orchestrator turn (matches the
- 2026-06-10 [claude]: committed 9cc43456: src/core/thinking_os/tools/cognition.py, src/core/web/routes/cognition.py, src/core/web/ui/src/featu
- 2026-06-10 [claude]: Status transitioned to complete via cos task-done.
