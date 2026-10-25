---
id: TASK-1076
title: "Keep tests away from the real Hub: COS_HUB_DIR override for hub.pid/hub.log"
swimlane: infra
kind: bug
epic: null
labels: [docs-update, ready]
status: complete
priority: P1
appetite: 2h
created: 2026-10-25
started: 2026-10-24
completed: 2026-10-24
agent_session: ses-claude-20261024-131905-031f
depends_on: []
blocked_by: []
references: []
---
# TASK-1076: Keep tests away from the real Hub: COS_HUB_DIR override for hub.pid/hub.log

**Outcome (one sentence):** No test can stop, restart or read the operator's running Hub: hub state resolves through COS_HUB_DIR, which the autouse test fixture points at a temp dir.

## Read First
- src/cli/_hub_paths.py
- tests/conftest.py
- src/cli/update.py
- docs/engineering/hub-architecture.md

## Repro Steps
Run tests/test_cli.py from a clone of the repo while `cos hub start` runs from the main checkout: `cos update` inside the suite restarts the Hub with the clone's code (PPID 1, `<clone>/.venv/bin/cos hub start --foreground`). Deleting the clone leaves the Hub serving 503 (ModuleNotFoundError) and the panel no longer opens.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the CLI suite runs `cos update` while a real Hub is up, **When** the update decides the hub code is stale, **Then** it reads hub.pid from the test's temp dir and the real Hub keeps running.
- **Given** COS_HUB_DIR is set, **When** any hub command resolves hub.pid or hub.log, **Then** both live under that dir; unset, they stay in ~/.coding-os.

## Work Log
- 2026-10-25 [claude]: Status transitioned to complete via cos task-done.
