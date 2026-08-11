---
id: TASK-936
title: "fix: stop the mypy count ratchet from counting test files"
swimlane: infra
kind: chore
epic: null
labels: [ready]
status: in_progress
priority: P2
appetite: 1d
created: 2026-08-11
started: 2026-08-11
completed: null
agent_session: ses-claude-20260807-224955-abc1
depends_on: []
blocked_by: []
references: []
---
# TASK-936: fix: stop the mypy count ratchet from counting test files

**Outcome (one sentence):** The mypy count ratchet measures src/core source only; test files leave the count SCOPE while staying in FATAL_SCOPE, and BASELINE is reset from a CI-measured log so a test-suite refactor can no longer trip a volume gate.

## Work Log
- 2026-08-11 [claude]: Edit mypy_ratchet.py
- 2026-08-11 [claude]: Edit ci-gates.md
- 2026-08-11 [claude]: Edit ci-gates.md
