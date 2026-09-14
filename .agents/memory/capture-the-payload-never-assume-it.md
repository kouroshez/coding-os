---
name: capture-the-payload-never-assume-it
description: Claude Code sends no exit_code for Bash; the event name is the outcome. Capture a real hook payload before writing logic against its shape.
metadata: 
  node_type: memory
  type: reference
  originSessionId: 5ac9fe2e-f9a3-4490-bb81-1ab2bb139298
  modified: 2026-09-14T02:34:26.117Z
---

Claude Code's Bash hook payloads carry **no `exit_code` field at all**. The outcome is the event name:

| Outcome | `hook_event_name` | `tool_response` | top-level `error` |
|---|---|---|---|
| success | `PostToolUse` | `{stdout, stderr, interrupted, isImage, noOutputExpected}` | absent |
| failure | `PostToolUseFailure` | absent (None) | set |

**Why:** `record-verify-auto.sh` read `.tool_response.exit_code // 0` and ledgered PASS for every run — `enforce-verify.sh` reads that ledger to let `cos task-done` through, so a suite nobody ran gated tasks closed. My first fix ("skip when exit_code is missing") then disabled the ledger entirely on the only runtime that uses it, and the next commit blocked.

**How to apply:** before writing logic against a hook payload's shape, capture one. Temporarily `printf %s "$INPUT" > <scratchpad>/payload.json` at the top of the hook, run a command that triggers it, then read the file — the hook fires *after* the tool call, so a `python3` in the same Bash call sees nothing; read it in the next call. Remove the probe immediately. Related: [[fail-open-hooks-hide-dead-triggers]], [[run-the-feature-not-just-its-tests]].
