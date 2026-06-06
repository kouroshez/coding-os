---
id: TASK-217
title: "Review hardening \u2014 anchor commit-grep, fail-safe on git error, log archive failures, strengthen reconcile test"
swimlane: core
kind: refactor
epic: task-lifecycle-integrity
labels: [workflow-integrity, board, lifecycle, review-fix, ready]
status: in_progress
priority: P2
appetite: 1d
created: 2026-06-06
started: 2026-06-06
completed: null
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-217: Review hardening — anchor commit-grep, fail-safe on git error, log archive failures, strengthen reconcile test

**Outcome (one sentence):** Adversarial-review findings on the reconciliation code are fixed: (1) _commits_referencing anchors the git --grep so TASK-215 no longer matches TASK-2155; (2) it returns None on git error (no repo / git missing) and the classifier/reclaim treat can't-verify as likely-complete (fail-safe — never reclaim/recycle on an unverifiable signal); (3) _archive_stale_sweep logs per-task transition failures instead of silently dropping; (4) the read-only reconcile test is strengthened to call twice and assert no mutation. Refuted findings (SQLi guard exists, nightly table-check exists, env try/finally exists) documented, not changed.

## Read First
- src/core/board_os/mcp_tools.py
- docs/tasks/audits/audit-task-lifecycle-integrity-2026-06-05.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a commit referencing TASK-2155, **When** `_commits_referencing("TASK-215", ...)` runs, **Then** it does NOT count that commit (anchored grep, trailing non-digit boundary).
- **Given** a project with no git repo (or git error), **When** `_commits_referencing` runs, **Then** it returns None (can't-verify) and the classifier treats the task as likely_complete / needs_review — never likely_abandoned and never auto-reclaimed (fail-safe).
- **Given** `_archive_stale_sweep` and a per-task `transition()` that fails, **When** the sweep runs, **Then** the failure is logged (not silently dropped).
- **Given** the read-only reconcile test, **When** it runs, **Then** it calls reconcile twice and asserts the board state is unchanged both times.
- **Then** matrix verification (board_os) green and a reviewer confirms env-error fail-safe direction.

## Work Log
