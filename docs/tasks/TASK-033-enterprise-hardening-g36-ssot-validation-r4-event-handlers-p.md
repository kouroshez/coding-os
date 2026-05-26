---
id: TASK-033
title: "Enterprise hardening — G36 SSOT validation + R4 event handlers + P6 per-thread sqlite"
swimlane: infra
kind: feature
epic: null
labels: [graph_os, enterprise, deferred-from-032, validation, concurrency]
status: complete
priority: P1
appetite: "1d"
created: 2026-05-26
started: 2026-05-25
completed: 2026-05-25
agent_session: ses-claude-20260525-225648-639f
depends_on: []
blocked_by: []
references: []
---
# TASK-033: Enterprise hardening — G36 SSOT validation + R4 event handlers + P6 per-thread sqlite

**Outcome (one sentence):** Three deferred-from-TASK-032 items landed for enterprise scale: G36 _shared.py validation SSOT used by all cos_* tools; R4 contracts.py extension emits handles_event for @router.subscribe / @bus.on / SSE patterns; P6 per-thread sqlite3 connection pool unblocks concurrent reads in Hub UI multi-tab + parallel MCP sessions. Reviewer subagent PASS.

## Read First
- docs/engineering/graph-os-deep-audit-findings-2026-05-25.md
- docs/engineering/graph-os-deep-audit-fix-checklist-2026-05-25.md
- src/core/thinking_os/tools/_shared.py
- src/core/graph_os/backends/sqlite_backend.py
- src/core/graph_os/extractors/contracts.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** TASK-032 audit register lists G36/R4/P6 as deferred-non-blocking,
- **When** all three land with regression coverage + reviewer PASS,
- **Then** graph_os pytest stays green, contracts.py emits ≥10 handles_event edges live, per-thread sqlite stress test shows parallel reads faster than sequential, and `_shared.py` exposes enum_or_fail + clamp_or_fail used by ≥3 tools.

## Work Log
- 2026-05-26 [claude]: Three enterprise hardening fixes landed
