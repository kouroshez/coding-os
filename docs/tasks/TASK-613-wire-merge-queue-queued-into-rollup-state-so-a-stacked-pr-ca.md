---
id: TASK-613
title: "Wire merge-queue QUEUED into _rollup_state so a stacked-PR cascade is isolated, not blocking"
swimlane: core
kind: bug
epic: git-foundation-hardening
labels: [pr-mode, merge-queue, code-review, ready]
status: archive
priority: P1
appetite: 1d
created: 2026-06-27
started: 2026-06-27
completed: 2026-06-27
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-613: Wire merge-queue QUEUED into _rollup_state so a stacked-PR cascade is isolated, not blocking

**Outcome (one sentence):** The rollup has no DISTINCT `queued` state — `_pr_ci_rollup` already folds GitHub's `QUEUED` status into a `waiting` set that returns `pending` (pr_commands.py ~line 906/914), so the driver cannot tell "in the merge queue, just wait" from "checks pending" and cannot detect a queue-EJECTION (a PR kicked out because it broke combined-with-main); add a distinct `queued` ci_rollup + an ejected/red distinction and make the pr-mode-driver wait (not re-submit/re-poll) on `queued`, so a stacked-PR cascade is isolated by the queue instead of blocking followers.

## Read First
- src/cli/pr_commands.py
- src/core/skills/pr-mode-driver/SKILL.md
- docs/playbooks/pr-workflow.md
- .github/workflows/ci.yml

## Repro Steps
Workflow whdjyvqjq + review (agent: NEEDS-EDIT — factual correction). Verified: `_rollup_state` returns merged|closed|pending|red|review-required|passing-unarmed|passing — NO `queued`; AND `_pr_ci_rollup` line ~906 puts `QUEUED` in a `waiting` set that maps to `pending` (line ~914), so a queued PR currently reads as `pending` (not crashed, but indistinguishable). ci.yml triggers CI on `merge_group` (line 16). Confirm the exact GitHub signal for a queued PR (statusCheckRollup state vs `mergeQueueEntry`/`mergeStateStatus` from `gh pr view`) before wiring — do not assume `QUEUED` is the only signal.

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** a PR sitting in the GitHub merge queue, **When** `cos pr status --branch` runs, **Then** ci_rollup reports a DISTINCT `queued` (not `pending`) and the pr-mode-driver waits without re-submitting. **Given** a PR EJECTED from the queue (broke when combined with main), **When** status runs, **Then** it reports a distinct failure (e.g. `red` with an ejected reason) so only that PR is healed while the rest keep merging. **Given** no merge queue configured, **Then** behavior is byte-unchanged (back-compat). Verify: `uv run pytest tests/test_cli.py::TestCosPr -q` with new `_rollup_state` cases for queued + ejected driven by a mocked `gh pr view` payload.

## Work Log
- 2026-06-28 [claude]: Verified the real GitHub signal first (api-contract): gh pr view --json lacks mergeQueueEntry; the authoritative…
