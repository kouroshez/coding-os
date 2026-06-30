---
id: TASK-650
title: "Backfill runnable sample test to every stack template missing one + stack_lint existence gate"
swimlane: templates
kind: test
epic: stack-completeness-v2
labels: [sample-tests, stack-completeness, wave-2, ready]
status: complete
priority: P2
appetite: 2d
created: 2026-06-30
started: 2026-06-30
completed: 2026-06-30
agent_session: ses-claude-20260630-012042-78c9
depends_on: []
blocked_by: []
references: []
---
# TASK-650: Backfill runnable sample test to every stack template missing one + stack_lint existence gate

**Outcome (one sentence):** Every work-surface stack template ships ≥1 runnable sample test exercising existing sample code, and stack_lint enforces sample-test presence + scans makefile test targets — verified by test_template_scaffold.py + stack-lint across all 30 stacks.

## Read First
- docs/playbooks/template-authoring.md
- src/cli/stack_lint.py
- tests/test_template_scaffold.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a fresh scaffold of any work-surface stack, **When** the stack's documented test command runs, **Then** ≥1 sample test is discovered and exercises an existing scaffold symbol (no invented app code).
- **Given** `cos stack-lint`, **When** a non-exempt stack ships no sample test, **Then** it fails with a sample-test (row-15) violation; library and `*-plain` stacks stay exempt by design.
- **Given** the suite, **When** `test_template_scaffold.py` and `make docs-lint` run, **Then** all pass and scaffold-manifest parity holds.

## Work Log
- 2026-06-30 [claude]: Edit health_status.py
- 2026-06-30 [claude]: Edit test_health_status.py
- 2026-06-30 [claude]: Edit stack_lint.py
- 2026-06-30 [claude]: Edit stack_lint.py
- 2026-06-30 [claude]: Edit stack_lint.py
- 2026-06-30 [claude]: Edit sl_analyze.py
- 2026-06-30 [claude]: Edit wf_extract.py
- 2026-06-30 [claude]: Edit wf_extract.py
- 2026-06-30 [claude]: Edit stack_lint.py
- 2026-06-30 [claude]: Edit wf_apply.py
- 2026-06-30 [claude]: Edit stack.yaml
- 2026-06-30 [claude]: Edit stack.yaml
- 2026-06-30 [claude]: Edit stack.yaml
- 2026-06-30 [claude]: commit d46fb4dbb2 — test(templates): sample tests for 7 work-surface stacks + soft stack_lint sample-test gate
