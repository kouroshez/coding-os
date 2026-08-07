---
id: TASK-880
title: "DoD verify gate reads stale agent-scoped last-verify ledger instead of project ledger"
swimlane: "board_os"
kind: bug
epic: null
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-08-04
started: 2026-08-07
completed: 2026-08-07
agent_session: ses-claude-20260806-204356-2f94
depends_on: []
blocked_by: []
references: []
---
# TASK-880: DoD verify gate reads stale agent-scoped last-verify ledger instead of project ledger

## Outcome

`cos task-done` DoD freshness check (`_verify_state` in transition_gates_cli.py) reads the same ledger the verify runners write, so a just-run `make docs-lint` PASS is visible to the gate without COS_VERIFY_OVERRIDE.

## Repro Steps

1. Run `make docs-lint` in the repo root — `.coding-os/.last-verify.json` gets a PASS entry with a fresh ts.
2. Immediately run `cos task-done TASK-NNN` on a testing-status task.
3. Gate fails with DOD_VERIFY_STALE reporting an age that matches neither the project ledger (fresh) nor the agent-scoped copy — a third cwd-scoped path is being read, because `COS_STATE_DIR` is relative and the gate process does not share the agent's cwd.

## Read First

- src/core/board_os/transition_gates_cli.py `_verify_ledger_path` / `_verify_state`
- src/core/thinking_os/database.py `project_root`
- docs/engineering/state-files.md (ledger ownership)

## Acceptance

- **Given** a fresh PASS in `<project>/.coding-os/.last-verify.json`
- **When** the DoD gate runs from a process whose cwd is not the project root
- **Then** it resolves the same project ledger and reports the fresh age, instead of a third cwd-scoped copy.

## Work Log
- 2026-08-07 [claude]: FIXED (7bb6cc44): root cause was COS_STATE_DIR being a relative path resolved against the gate process's cwd — the…
- 2026-08-07 [claude]: Status transitioned to complete via cos task-done.
- 2026-08-07 [claude]: commit f8932a64be — chore(board): close TASK-880 and TASK-882, log the cos update P0 fix
- 2026-08-07 [claude]: commit eaf72ded16 — style: apply ruff format to the supervision change set
- 2026-08-07 [claude]: Edit test_cognition_tools.py
- 2026-08-07 [claude]: commit 0a245206d4 — test(supervision): drop a hardcoded model id from the clear-flag guard test
- 2026-08-07 [claude]: Edit README.md
- 2026-08-07 [claude]: Edit README.md
- 2026-08-07 [claude]: Edit README.md
- 2026-08-07 [claude]: commit 299c4f033f — docs(readme): correct the supervision cooldown scope and list the command
