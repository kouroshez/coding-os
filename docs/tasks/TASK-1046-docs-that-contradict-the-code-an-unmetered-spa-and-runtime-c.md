---
id: TASK-1046
title: "Docs that contradict the code, an unmetered SPA, and runtime cruft nobody reclaims"
swimlane: infra
kind: chore
epic: null
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-09-18
started: 2026-09-18
completed: 2026-09-18
agent_session: ses-claude-20260918-164827-6f4a
depends_on: []
blocked_by: []
references: []
---
# TASK-1046: Docs that contradict the code, an unmetered SPA, and runtime cruft nobody reclaims

**Outcome (one sentence):** Every number a doc quotes matches the code it describes, the SPA's one real gate is pinned to its measured value, and the runtime artifacts the product leaves behind are either reclaimed or named.

## Work Log
- 2026-09-18 [claude]: Edit patch_reclaimable.py
- 2026-09-18 [claude]: commit 8b49b61baf — feat(doctor): report how much of an over-budget DB a VACUUM would return
- 2026-09-18 [claude]: Status transitioned to complete via cos task-done.
- 2026-09-19 [claude]: Closed all three strands. Docs: mypy 1100→1078, nightly recorded as gating since 313b4ee5, suite size 4,850→8,510,…
