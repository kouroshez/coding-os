---
id: TASK-505
title: "Consumer-disable integration harness \u2014 assert no orphaned artifacts end-to-end (modularity CI guard)"
swimlane: core
kind: test
epic: null
labels: [ready]
status: icebox
priority: P2
appetite: 1d
created: 2026-06-21
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-505: Consumer-disable integration harness — assert no orphaned artifacts end-to-end (modularity CI guard)

---
id: TASK-505
title: "Consumer-disable integration harness — assert no orphaned artifacts end-to-end (modularity CI guard)"
swimlane: core
kind: test
epic: null
labels: [ready]
status: icebox
priority: P2
appetite: 1d
created: 2026-06-21
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-505: Consumer-disable integration harness — assert no orphaned artifacts end-to-end (modularity CI guard)

**Outcome (one sentence):** One integration test scaffolds a real consumer, disables a single module, and asserts every artifact kind (hook, tool, skill, command, module-tagged doc) is gone — the durable guard against the half-wired over-claim pattern DOC-4/DOC-5 slipped through.

## Read First
- tests/test_cli.py
- src/cli/module_commands.py
- src/cli/subsystems.py
- src/core/subsystems.yaml

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** a freshly scaffolded real consumer
**When** one module (e.g. tasks) is disabled via the runtime toggle
**Then** the test asserts no owned hook in the allowlist, no owned tool in list_tools, no owned skill symlink, no owned command symlink, AND surfaces (xfail/known-gap) any module-tagged doc still present; the harness is single-module (not a matrix) and runs in the fast PR test-modularity job, not @slow.

## Work Log
