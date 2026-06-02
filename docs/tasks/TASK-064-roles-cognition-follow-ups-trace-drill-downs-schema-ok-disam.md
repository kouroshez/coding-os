---
id: TASK-064
title: "Roles/Cognition follow-ups: trace drill-downs, schema_ok disambiguation, audit unconsumed role config"
swimlane: thinking_os
kind: chore
epic: null
labels: []
status: icebox
priority: P2
appetite: "1d"
created: 2026-06-02
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-064: Roles/Cognition follow-ups: trace drill-downs, schema_ok disambiguation, audit unconsumed role config

**Outcome (one sentence):** Deferred from TASK-063 (panel now shows real composed chains). Lower-priority polish: (1) RolesPage planned/composed rows link to the originating compose_done trace + cost→formula→session cross-links; (2) disambiguate schema_ok=null between bundle-missing vs schema-import-failure in roles.py + UI; (3) optional persona_selections parity from the auto-compose path (analytics); (4) audit role-config knobs flagged unconsumed-at-runtime (parallel_dispatch, action handlers, backtrack_triggers, intensity_steps, chain_notes) — but note roles/README.md + doctor C28 treat intensity_steps/backtrack_triggers as agent-prompt contract, so resolve = either wire them or remove WITH README/doctor alignment, not a blind cut. None of these block panel correctness; do only if they earn their diff.

## Work Log
