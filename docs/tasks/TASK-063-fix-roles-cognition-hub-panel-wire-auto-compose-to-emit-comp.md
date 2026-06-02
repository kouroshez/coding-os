---
id: TASK-063
title: "Fix Roles/Cognition Hub panel: wire auto-compose to emit compose_done + truthful UI + doc align"
swimlane: thinking_os
kind: bug
epic: null
labels: []
status: complete
priority: P2
appetite: "1d"
created: 2026-06-02
started: 2026-06-02
completed: 2026-06-02
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-063: Fix Roles/Cognition Hub panel: wire auto-compose to emit compose_done + truthful UI + doc align

**Outcome (one sentence):** Roles Hub panel reflects real in-session role composition. Root cause: auto-compose hook (the only path that fires in-session) stamps markers but never emits compose_done, while the panel's evidence/planned view reads compose_done + role_output_recorded — so it is always empty. Fix: shared roles_state.record_compose_traces() emitted by BOTH auto_compose.py and cos_compose_chain (SSOT, no drift); RolesPage labels distinguish in-session-planned vs SDK-dispatched-executed; CLAUDE.md presets path + roles docs aligned.

## Read First
- src/core/thinking_os/roles_state.py
- src/core/hooks/_helpers/auto_compose.py
- src/core/web/routes/roles.py
- src/core/web/ui/src/pages/RolesPage.tsx

## Repro Steps
1. Open the Hub (`cos hub start`) → Cognition → ROLES tab; select any role (e.g. analyst).
2. Work a COMPLICATED/COMPLEX task so `auto-compose-roles.sh` fires and stamps `.roles`/`.role`.
3. Observe the EVIDENCE pane.
Expected: the composed chain shows the role as "planned" (chain was composed this session).
Actual: "0 executed · 0 planned / No traces reference <role> yet" — auto_compose stamps markers but never emits `compose_done`, so the panel (which reads `compose_done`) sees nothing. Only 1 `persona_selections` row + 0 `compose_done` events exist across all sessions.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a session whose gate is COMPLICATED/COMPLEX so the auto-compose hook runs,
- **When** `auto_compose.py` composes a chain and stamps the markers,
- **Then** it emits a `compose_done` trace (via shared `roles_state.record_compose_traces`) to the agent-level traces dir, the Roles panel shows each chain member as "planned", `cos_compose_chain` uses the same shared emitter (no second emit site), the RolesPage empty-state/labels distinguish in-session-planned from SDK-dispatched-executed, CLAUDE.md's roles `presets/registry.yaml` path is corrected, and matrix verification (roles_state/cognition pytest + ui typecheck + docs-lint) is green.

## Work Log
- 2026-06-02 [claude]: compose_done emitted by auto-compose via shared roles_state.record_compose_traces; RolesPage copy truthful; AGENTS path 
