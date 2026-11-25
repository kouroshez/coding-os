---
name: verify-ledger-needs-standalone-runs
description: task-done's DOD_VERIFY_STALE reads .last-verify.json, which only records matrix commands run standalone
metadata:
  type: feedback
---

`cos task-done` blocks with `DOD_VERIFY_STALE` when the newest PASS in `$COS_STATE_DIR/.last-verify.json` is older than 1800 s. The ledger only records a matrix command run on its own: `make verify-hooks > log 2>&1; echo $?` and `a && b` chains are never written, so a session can run the suites many times, all green, and still be refused at close.

**Why:** on 2026-11-25 TASK-1126 was refused at close with a 7-hour-old `verify-hooks` entry, after every round had run `make verify-hooks` wrapped in a redirect-and-echo chain.

**How to apply:** run the final matrix commands at close as bare standalone commands (`make verify-hooks`, `uv run pytest <row> -q`), not wrapped for log capture. Related: [[pytest-piped-to-tail-hides-failures]].
