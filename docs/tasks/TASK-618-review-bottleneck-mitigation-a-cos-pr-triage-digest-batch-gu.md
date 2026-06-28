---
id: TASK-618
title: "Review-bottleneck mitigation: a cos pr triage digest + batch guidance for the away-human stacked-PR pileup"
swimlane: core
kind: feature
epic: git-foundation-hardening
labels: [pr-mode, review, product, ready]
status: complete
priority: P2
appetite: 1d
created: 2026-06-27
started: 2026-06-27
completed: 2026-06-27
agent_session: ses-claude-20260625-235014-c028
depends_on: []
blocked_by: []
references: []
---
# TASK-618: Review-bottleneck mitigation: a cos pr triage digest + batch guidance for the away-human stacked-PR pileup

**Outcome (one sentence):** In draft, a human away all day returns to N open agent PRs and must review them one-by-one with no prioritization — the owner's explicit fear. Add `cos pr triage`: a single digest of all open agents/* PRs with ci_rollup + review state + conflict risk (cos pr conflicts) + age, RANKED so the human reviews highest-value / lowest-risk / unblock-the-most first; and document the auto_merge-with-strong-CI path that removes the human from the hot path entirely. Honest scope: draft inherently keeps the human as the gate — this makes the gate FAST and informed, it does not eliminate it.

## Read First
- src/cli/pr_commands.py
- docs/playbooks/pr-workflow.md
- docs/playbooks/multi-agent-git-use-cases.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** several open agents/* PRs, **When** `cos pr triage` runs, **Then** it emits one ranked digest (per PR: ci_rollup, review state, conflict risk, age) ordered to minimize the human's time-to-unblock. **Given** a PR that is green + conflict-free + no required review, **Then** it is flagged as a safe quick-merge. **Given** no open PRs, **Then** a clean empty report. Verify: `uv run pytest tests/test_cli.py::TestCosPr -q` with a mocked-gh triage case asserting the ranking.

## Work Log
- 2026-06-28 [claude]: Added `cos pr triage`: one gh-pr-list call → ranked digest of open agents/* PRs via _triage_entry (reuses…
