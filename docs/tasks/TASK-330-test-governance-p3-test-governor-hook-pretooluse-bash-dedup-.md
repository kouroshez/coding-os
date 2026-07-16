---
id: TASK-330
title: "Test-governance P3: test-governor hook \u2014 PreToolUse Bash dedup via ledger, flock lock, full-sweep block + audited override"
swimlane: core
kind: feature
epic: test-governance
labels: [test-governance, hooks, rule-20, ready]
status: archive
priority: P1
appetite: 1d
created: 2026-06-10
started: 2026-06-09
completed: 2026-06-09
agent_session: ses-claude-20260527-151803-0b9f
depends_on: [TASK-328, TASK-329]
blocked_by: []
references: []
---
# TASK-330: Test-governance P3: test-governor hook — PreToolUse Bash dedup via ledger, flock lock, full-sweep block + audited override

**Outcome (one sentence):** PreToolUse Bash hook BLOCKs: (a) re-run of a suite already green on the same tree within TTL (COS_TEST_FORCE=1 overrides), (b) suite run while .test-run.lock is held (names holder, never queue-waits), (c) full sweeps without COS_FULL_SWEEP_OK=1 + >=15-char reason; fail-open on internal errors; Codex Bash-matcher parity.

## Read First
- docs/engineering/test-governance.md
- src/core/hooks/registry.yaml
- src/core/hooks/enforce-verify.sh
- src/core/rules/git-workflow.md
- src/core/rules/test-discipline.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** synthetic payloads
- **When** duplicate fresh suite / lock held by live pid / bare pytest tests/ without override
- **Then** exit 2 with reuse msg, holder name, or override instructions respectively; override + reason allows and is logged; changed tree allows; killed lock-holder releases flock; verify-hooks + pytest green

## Work Log
- 2026-06-10 [claude]: Status transitioned to complete via cos task-done.
