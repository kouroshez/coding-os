---
id: TASK-616
title: "Prove the auto_merge loop end-to-end: a faithful mock-gh integration test (arm to green to merge to cleanup) plus one gated live validation"
swimlane: core
kind: chore
epic: git-foundation-hardening
labels: [pr-mode, merge-queue, testing, ready]
status: complete
priority: P1
appetite: 1d
created: 2026-06-27
started: 2026-06-27
completed: 2026-06-27
agent_session: ses-claude-20260625-235014-c028
depends_on: []
blocked_by: []
references: []
---
# TASK-616: Prove the auto_merge loop end-to-end: a faithful mock-gh integration test (arm to green to merge to cleanup) plus one gated live validation

**Outcome (one sentence):** The auto_merge/autonomous loop has NEVER run end-to-end (the GitHub Actions billing gate blocked every live CI run), so green→arm→merge→cleanup is unvalidated theatre and the reliability score cannot honestly exceed ~6. Add a stateful faithful mock-gh fixture that simulates the full lifecycle (PR open → required check pending→green → auto-merge arm → merge → head-branch delete → reaper cleanup) so the loop is proven in CI without minutes; AND define one EXTERNAL gated live validation (a single real run on a protected test repo once billing is restored) with a checklist. Clearly separates the code-now part (mock integration test) from the EXTERNAL part (live run).

## Work Log
- 2026-06-28 [claude]: Code-now part: stateful mock-gh (test_auto_merge_loop_end_to_end) drives open→submit(arm)→status…
