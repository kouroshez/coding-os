---
id: TASK-978
title: "Strip TASK-NNN provenance from source comments and lint it shut"
swimlane: core
kind: chore
epic: null
labels: [rule-12, dogfood, P2, ready]
status: complete
priority: P2
appetite: 1d
created: 2026-08-14
started: 2026-08-14
completed: 2026-08-14
agent_session: ses-claude-20260814-120316-413b
depends_on: []
blocked_by: []
references: []
---
# TASK-978: Strip TASK-NNN provenance from source comments and lint it shut

**Outcome (one sentence):** The repo stops violating its own Rule 12, and a lint gate keeps the next TASK-NNN reference out of a comment instead of relying on review to catch it.

## Work Log
- 2026-08-14 [claude]: Edit strip_task_refs.py
- 2026-08-14 [claude]: Edit fix_leftovers.py
- 2026-08-14 [claude]: Edit test_file_size_budget.py
- 2026-08-14 [claude]: Edit cos-env.sh
- 2026-08-14 [claude]: Edit test-governor.sh
- 2026-08-14 [claude]: Edit block-dangerous-commands.sh
- 2026-08-14 [claude]: Edit LiveAgentsPanel.tsx
- 2026-08-14 [claude]: Edit presence.ts
- 2026-08-14 [claude]: Edit OnboardingWizard.tsx
- 2026-08-14 [claude]: Edit msg13.txt
- 2026-08-14 [claude]: commit 96350c8f12 — refactor(comments): strip TASK-NNN provenance and gate it shut
- 2026-08-14 [claude]: Done in 96350c8f: 346 refs removed across 380 files, gate added to test_file_size_budget. Deliberately staged by…
- 2026-08-14 [claude]: Status transitioned to complete via cos task-done.
