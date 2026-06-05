---
id: TASK-105
title: "Harden danger/secret regex — rm -rf / · . · .. · * · -fr bypass, sk- false-positive, force-push refspec"
swimlane: core
kind: bug
epic: hook-remediation
labels: [safety, hooks, critical, audit-n2, ready]
status: icebox
priority: P0
appetite: "1d"
created: 2026-06-05
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-105: Harden danger/secret regex — rm -rf / · . · .. · * · -fr bypass, sk- false-positive, force-push refspec

**Outcome (one sentence):** block-dangerous-commands blocks rm -rf on /, ., .., *, ./, and flag-order variants (-fr, -r -f); force-push refspec (+main) caught; block-secrets sk- regex no longer false-fires on kebab slugs.

## Read First
- src/core/hooks/block-dangerous-commands.sh
- src/core/hooks/block-secrets.sh

## Repro Steps
1. (fill in: exact steps to reproduce)
2. ...
Expected: ...
Actual: ...

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** ...
- **When** ...
- **Then** ...

## Work Log
