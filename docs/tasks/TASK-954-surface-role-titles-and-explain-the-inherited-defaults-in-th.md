---
id: TASK-954
title: "Surface role titles and explain the inherited defaults in the supervision and chat pickers"
swimlane: core
kind: feature
epic: null
labels: [ready]
status: complete
priority: P1
appetite: 1d
created: 2026-08-12
started: 2026-08-12
completed: 2026-08-12
agent_session: ses-claude-20260807-224955-abc1
depends_on: []
blocked_by: []
references: []
---
# TASK-954: Surface role titles and explain the inherited defaults in the supervision and chat pickers

**Outcome (one sentence):** The roles endpoint emits each role's human title and canonical chain order, and the supervision and chat pickers render that title plus a stated meaning for each inherited default instead of a bare lowercase id and three unexplained "default" options.

## Read First
- src/core/web/routes/cognition_chat.py
- src/core/web/ui/src/features/cognition/roles.ts
- src/core/web/ui/src/pages/settings/ModelRoutingSection.tsx
- src/core/thinking_os/agents/reviewer.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** role definitions in thinking_os/agents/*.md that already carry a name and canonical_order
**When** the operator opens Agent Supervision or the chat composer's role picker
**Then** each role shows its human title ordered by canonical_order, and every inherited default states what it resolves to rather than reading "current adapter" or "adapter default" with no explanation.

## Work Log
- 2026-08-12 [claude]: Edit _cognition_chat_prompts.py
- 2026-08-12 [claude]: Edit cognition_chat.py
- 2026-08-12 [claude]: Edit cognition_chat.py
- 2026-08-12 [claude]: Edit roles.ts
- 2026-08-12 [claude]: Edit NewChatForm.tsx
- 2026-08-12 [claude]: Edit ModelRoutingSection.tsx
- 2026-08-12 [claude]: Edit ModelRoutingSection.tsx
- 2026-08-12 [claude]: commit 452172a1b9 — feat(hub): show role titles and name what each inherited default resolves to
- 2026-08-12 [claude]: Edit probe_routes.py
- 2026-08-12 [claude]: Status transitioned to complete via cos task-done.
