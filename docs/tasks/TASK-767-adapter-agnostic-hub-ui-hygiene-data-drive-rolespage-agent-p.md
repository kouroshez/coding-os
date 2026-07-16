---
id: TASK-767
title: "Adapter-agnostic Hub UI hygiene: data-drive RolesPage agent picker + presence.ts model label"
swimlane: core
kind: chore
epic: null
labels: [ready]
status: complete
priority: P3
appetite: 1d
created: 2026-07-04
started: 2026-07-04
completed: 2026-07-04
agent_session: ses-claude-20260703-211332-9106
depends_on: []
blocked_by: []
references: []
---
# TASK-767: Adapter-agnostic Hub UI hygiene: data-drive RolesPage agent picker + presence.ts model label

**Outcome (one sentence):** The two remaining production adapter hardcodes surfaced by audit pass-7 (D3-F1 RolesPage.tsx agent <option>s, D3-F3 presence.ts claude-only modelLabel regex) are data-driven so a new adapter (e.g. gemini) needs no UI edit and non-claude/single-integer model ids render prettily.

## Work Log
- 2026-07-04 [claude]: Edit RolesPage.tsx
- 2026-07-04 [claude]: Edit RolesPage.tsx
- 2026-07-04 [claude]: Edit presence.ts
- 2026-07-04 [claude]: Edit presence.test.ts
- 2026-07-04 [claude]: Status transitioned to complete via cos task-done.
