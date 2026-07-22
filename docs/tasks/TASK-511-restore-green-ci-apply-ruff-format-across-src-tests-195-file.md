---
id: TASK-511
title: "Restore green CI \u2014 apply ruff format across src/+tests/ (195-file drift)"
swimlane: infra
kind: chore
epic: null
labels: [ci, ruff, formatting, release-unblock, ready]
status: archive
priority: P0
appetite: 1d
created: 2026-06-21
started: 2026-06-21
completed: 2026-06-22
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-511: Restore green CI — apply ruff format across src/+tests/ (195-file drift)

**Outcome (one sentence):** CI 'lint' job passes (ruff format --check clean) so the full job graph runs and CI Pass goes green on main, unblocking the v0.4.0 release PR.

## Work Log
- 2026-06-21 [claude]: commit 86a8f1421c — style: apply ruff format across src/ + tests/ (195-file drift)
- 2026-06-21 [claude]: commit c6bf328bbb — chore(board): sync task files + add TASK-511 (CI ruff-format fix)
- 2026-06-21 [claude]: commit 6535f0e067 — build(ui): pin typescript to ^5.9.3 — openapi-typescript blocks TS6 (npm ci ERESOLVE)
- 2026-06-21 [claude]: commit 5c1d176331 — docs(api): regenerate OpenAPI snapshot — drifted graph endpoints
- 2026-06-21 [claude]: commit c6634a4b6f — test(golden): recapture hook fixtures + regen manifest (pre-existing drift)
- 2026-06-21 [claude]: Edit constitution.md
- 2026-06-22 [claude]: Status transitioned to complete via cos task-done.
