---
id: TASK-065
title: "Strengthen roles: inject lead-role directive into compose nudge + chain consistency from trace"
swimlane: thinking_os
kind: feature
epic: null
labels: []
status: complete
priority: P2
appetite: "1d"
created: 2026-06-03
started: 2026-06-03
completed: 2026-06-03
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-065: Strengthen roles: inject lead-role directive into compose nudge + chain consistency from trace

**Outcome (one sentence):** Make the automatic role layer actually guide behavior + show a consistent chain. Item 1: auto_compose._compose_roles appends the lead role's prompt_prefix first line (read from roles/<lead>.yaml, ≤2 lines) to the compose nudge so the agent gets real guidance, not just a label. Item 2: /api/roles/chain derives the displayed chain from the newest agent-level compose_done trace (reliable post-TASK-063), keeps the .role marker for active role, falls back to marker — fixes the multi-panel mismatch (chain=['analyst'] while active=reviewer). Both graph-verified zero-consumer-break.

## Read First
- src/core/hooks/_helpers/auto_compose.py
- src/core/web/routes/roles.py
- src/core/thinking_os/roles_state.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a COMPLICATED/COMPLEX gate so auto-compose fires, and a panel whose newest compose_done trace differs from a stale `.roles` marker,
- **When** the UserPromptSubmit hook composes a chain, and the Hub fetches `/api/roles/chain`,
- **Then** the compose nudge additionalContext includes the lead role's prompt_prefix directive (≤2 lines, read from `roles/<lead>.yaml`, fail-open if absent), AND `/api/roles/chain` returns the chain from the newest agent-level compose_done trace (active role still from `.role`, marker fallback when no trace) so chain and active role are consistent — response shape unchanged, existing tests green, plus new assertions for both behaviors.

## Work Log
- 2026-06-03 [claude]: Item1 lead-role directive in nudge + Item2 chain-from-trace done. 1266 thinking_os + 5 roles tests green. Found pre-exis
