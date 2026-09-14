---
id: TASK-1034
title: "record-verify-auto defaults a missing exit_code to 0 and records PASS"
swimlane: infra
kind: bug
epic: null
labels: [ready]
status: icebox
priority: P2
appetite: 1d
created: 2026-09-14
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-1034: record-verify-auto defaults a missing exit_code to 0 and records PASS

**Outcome (one sentence):** A suite whose exit code the runtime never reported is recorded as nothing at all, so the verify ledger can no longer hand `cos task-done` a green light it never earned.

## Read First
- src/core/hooks/record-verify-auto.sh
- src/core/hooks/enforce-verify.sh (the ledger's consumer)
- src/core/rules/test-discipline.md § Enforcement + the verify ledger

## Repro Steps
1. Feed the hook a PostToolUse payload for a matrix suite whose `tool_response`
   carries no `exit_code` — stdout saying `1 failed, 2 passed` is enough:
   `printf '{"hook_event_name":"PostToolUse","tool_name":"Bash","tool_input":{"command":"make docs-lint"},"tool_response":{"stdout":"1 failed, 2 passed"}}' | bash src/core/hooks/record-verify-auto.sh`
2. Measured 2026-09-13: `.last-verify.json` records `docs-lint: PASS`,
   byte-identical to a run that really exited 0.
3. Root cause: `jq -r '.tool_response.exit_code // ... // 0'` cannot tell an
   absent field from a zero one. The `PostToolUseFailure` branch was already
   hardened against exactly this, but the ordinary PostToolUse path was not.
Expected: the real outcome, or no record when it is genuinely unknown.
Actual: PASS — and `enforce-verify.sh` reads this ledger to decide whether
`cos task-done` may close a task, so the phantom pass opens the gate.

## The payload contract, captured rather than assumed

Claude Code sends **no `exit_code` for Bash at all**, so "skip when exit_code
is missing" would have disabled the ledger on the only runtime that uses it —
the first attempt at this fix did exactly that, and the next `cos task-done`
blocked. A live capture settled the real shape:

| Outcome | event | `tool_response` | top-level `error` |
|---|---|---|---|
| success | `PostToolUse` | `{stdout, stderr, interrupted, isImage, noOutputExpected}` | absent |
| failure | `PostToolUseFailure` | absent | set |

The event is the outcome. An explicit `exit_code` still wins when a runtime
sends one; only a payload with neither signal records nothing.

**Residual, deliberately not fixed here:** a suite that fails inside a compound
command whose shell still exits 0 (`make x || true`, or a pipeline) arrives as
a success event. The hook can only report what the runtime tells it; the
defence against that is the operator not burying a suite behind `|| true`.

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** a matrix-suite payload carrying no `exit_code`
**When** record-verify-auto runs
**Then** nothing is written to the ledger, and the skip is logged with its
reason so the silence is explainable.

**Given** a payload carrying `exit_code: 0`
**When** the hook runs
**Then** PASS is still recorded — the fix must not disable the ledger.

**Given** a `PostToolUseFailure` event with no `exit_code`
**When** the hook runs
**Then** FAIL is recorded, because the event itself is the outcome.

## Work Log
