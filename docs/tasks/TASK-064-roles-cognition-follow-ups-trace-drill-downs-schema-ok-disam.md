---
id: TASK-064
title: "Roles/Cognition follow-ups: trace drill-downs, schema_ok disambiguation, audit unconsumed role config"
swimlane: thinking_os
kind: chore
epic: null
labels: []
status: archive
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
# TASK-064: Roles/Cognition follow-ups: trace drill-downs, schema_ok disambiguation, audit unconsumed role config

**Outcome (one sentence):** Finish the roles/cognition follow-ups after TASK-063. (0) [option-a, chosen] Gate Path B honestly: /api/roles exposes `dispatch_available` and RolesPage shows a sub-agent-dispatch capability indicator so "dispatched: 0" reads as capability-off (SDK extra) not a bug; (1) disambiguate schema_ok=null between no-payload vs no-schema in roles.py + UI; (2) audit role-config knobs flagged unconsumed-at-runtime (parallel_dispatch, backtrack_triggers, intensity_steps, chain_notes) — roles/README.md + doctor C28 treat several as agent-prompt contract, so resolve = wire-or-keep with a documented finding, NOT a blind cut; (3) trace drill-down per row already exists via the "open trace" link — cost→formula cross-links are a Path-B feature, skipped as not-earned. persona_selections parity skipped (analytics, no panel consumer).

## Work Log
- 2026-06-02 [claude]: Config-knob audit: NO cut. intensity_steps (cognition.py:90) + parallel_layers (formula_composer:292) runtime-consumed; 
