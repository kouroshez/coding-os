---
id: TASK-190
title: "Unify the two divergent presence classifiers to one SSOT"
swimlane: core
kind: refactor
epic: agent-hub
labels: [ready]
status: archive
priority: P2
appetite: "4h"
created: 2026-06-06
started: 2026-06-05
completed: 2026-06-05
agent_session: ses-claude-20260605-183120-db30
depends_on: []
blocked_by: []
references: []
---
# TASK-190: Unify the two divergent presence classifiers to one SSOT

**Outcome (one sentence):** /api/sessions/active and cos_presence_query agree on a session's state by delegating both to the single board_os.presence classifier, retiring the divergent web/routes/sessions.py thresholds.

## Read First
- docs/engineering/agent-hub-orchestration.md
- src/core/web/routes/sessions.py
- src/core/board_os/presence.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the same presence JSON for a session
- **When** it is classified by /api/sessions/active and by cos_presence_query
- **Then** both yield the same lifecycle verdict from the shared board_os.presence classifier (no second vocabulary/threshold in sessions.py); a test asserts parity; presence + web tests stay green.

## Work Log
- 2026-06-06 [claude]: web/routes/sessions.py::_classify now delegates the core verdict to board_os.presence.session_presence (single SSOT, 90s
