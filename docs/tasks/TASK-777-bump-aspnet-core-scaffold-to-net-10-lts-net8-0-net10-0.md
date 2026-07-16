---
id: TASK-777
title: "Bump aspnet-core scaffold to .NET 10 LTS (net8.0 \u2192 net10.0)"
swimlane: core
kind: chore
epic: null
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-07-04
started: 2026-07-04
completed: 2026-07-04
agent_session: ses-claude-20260703-210450-473d
depends_on: []
blocked_by: []
references: []
---
# TASK-777: Bump aspnet-core scaffold to .NET 10 LTS (net8.0 → net10.0)

**Outcome (one sentence):** The aspnet-core seed targets net10.0 (current LTS, Nov 2025, supported to Nov 2028) instead of net8.0 (support ends Nov 2026), so a 2026 `cos init` is not seeded one LTS behind.

## Work Log
- 2026-07-04 [claude]: Edit Backend.csproj
- 2026-07-04 [claude]: Edit Backend.Tests.csproj
- 2026-07-04 [claude]: commit eac5db56c9 — chore(templates): bump aspnet-core scaffold to .NET 10 LTS
- 2026-07-04 [claude]: Status transitioned to complete via cos task-done.
