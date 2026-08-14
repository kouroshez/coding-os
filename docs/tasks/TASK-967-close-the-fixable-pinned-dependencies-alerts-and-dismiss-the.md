---
id: TASK-967
title: "Close the fixable Pinned-Dependencies alerts and dismiss the rest with evidence"
swimlane: infra
kind: chore
epic: null
labels: [supply-chain, ci, ready]
status: in_progress
priority: P1
appetite: 1d
created: 2026-08-14
started: 2026-08-13
completed: null
agent_session: ses-claude-20260812-170221-1654
depends_on: []
blocked_by: []
references: []
---
# TASK-967: Close the fixable Pinned-Dependencies alerts and dismiss the rest with evidence

**Outcome (one sentence):** Code scanning shows zero open alerts: the build-time pip install is hash-pinned, and every alert that cannot be fixed carries a per-alert dismissal naming the concrete blocker instead of sitting as permanent noise.

## Work Log
- 2026-08-14 [claude]: Edit requirements-build.txt
- 2026-08-14 [claude]: Edit release-please.yml
- 2026-08-14 [claude]: Edit install.sh
- 2026-08-14 [claude]: Edit install.sh
