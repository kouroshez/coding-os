---
id: TASK-936
title: "fix: stop the mypy count ratchet from counting test files"
swimlane: infra
kind: chore
epic: null
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-08-11
started: 2026-08-11
completed: 2026-08-11
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
- 2026-08-11 [claude]: commit 8d34505715 — chore(gates): record the mypy count rise the test-suite split produced
- 2026-08-11 [claude]: commit 072b0097a2 — fix(ci): repoint the workflow, Makefile and scan-ignore paths at the split test modules
- 2026-08-11 [claude]: commit 48f23c223c — chore(golden): recapture the fixtures for the Rule 27 hook and skill changes
- 2026-08-11 [claude]: commit f6427d86f2 — chore(board): park TASK-936 as ready icebox work
- 2026-08-11 [claude]: commit 8671f57be7 — chore(memory): refresh the lesson index and TASK-936 work log
- 2026-08-11 [claude]: Edit mypy_ratchet.py
- 2026-08-11 [claude]: Edit mypy_ratchet.py
- 2026-08-11 [claude]: Edit ci-gates.md
- 2026-08-11 [claude]: Edit ci-gates.md
- 2026-08-11 [claude]: Edit ci-gates.md
- 2026-08-11 [claude]: commit b2b80aa538 — fix(gates): measure the mypy count over kernel source, not test preambles
- 2026-08-11 [claude]: Status transitioned to complete via cos task-done.
