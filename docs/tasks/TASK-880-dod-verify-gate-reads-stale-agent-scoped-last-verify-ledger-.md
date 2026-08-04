---
id: TASK-880
title: "DoD verify gate reads stale agent-scoped last-verify ledger instead of project ledger"
swimlane: "board_os"
kind: bug
epic: null
labels: [ready]
status: icebox
priority: P2
appetite: 1d
created: 2026-08-04
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-880: DoD verify gate reads stale agent-scoped last-verify ledger instead of project ledger

## Outcome

`cos task-done` DoD freshness check (`_verify_state` in transition_gates_cli.py) reads the same ledger the verify runners write, so a just-run `make docs-lint` PASS is visible to the gate without COS_VERIFY_OVERRIDE.

## Repro Steps

1. Run `make docs-lint` in coding-os root — `.coding-os/.last-verify.json` gets a PASS entry with fresh ts (verified age<120s).
2. Immediately run `cos task-done TASK-NNN` on a testing-status task.
3. Gate fails with DOD_VERIFY_STALE reporting an age (~12h) that matches neither `.coding-os/.last-verify.json` (fresh) nor `.coding-os/claude/.last-verify.json` (58 days) — some third scoped copy (MCP/board process CWD or COS_STATE_DIR) is being read.

## Read First

- src/core/board_os/transition_gates_cli.py `_verify_state` (COS_STATE_DIR default ".coding-os" is CWD-relative)
- src/core/board_os/workflow.py DoD wiring (~line 553)
- docs/engineering/state-files.md (ledger ownership)

## Acceptance

- Given a fresh PASS in the project ledger, when task-done runs from any entrypoint (CLI, MCP, hub), then DOD_VERIFY_STALE does not fire.
- Given no recent PASS anywhere, when task-done runs, then the gate still blocks.

## Work Log
