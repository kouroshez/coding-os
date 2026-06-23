---
id: TASK-521
title: "CI merge-queue (merge_group) + branch-protection/ruleset docs + consumer-fixture dogfood test"
swimlane: infra
kind: feature
epic: multi-agent-pr-mode
labels: [pr-mode, ci, dogfood]
status: icebox
priority: P2
appetite: 1d
created: 2026-06-22
started: null
completed: null
agent_session: null
depends_on: [TASK-518]
blocked_by: []
references: []
---

# TASK-521: CI merge-queue (merge_group) + branch-protection/ruleset docs + consumer-fixture dogfood test

**Outcome (one sentence):** ci.yml gains a merge_group trigger so N PRs into integration are serialized server-side (fixes the rebase thundering-herd/livelock). The GitHub branch-protection/ruleset + auto-merge + auto-delete-head setup is documented in the playbook (it cannot live in-repo). A consumer-fixture project exercises pr-mode end-to-end in CI so coding-os dogfoods the capability WITHOUT itself flipping to pr-mode. Gated until TASK-513 (green CI + Actions quota) closes.

## Read First
- .github/workflows/ci.yml
- docs/playbooks/pr-workflow.md
- docs/governance/critical-rules.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** ci.yml with a merge_group trigger, **When** a merge_group event fires, **Then** the CI Pass gate runs on the queued combination. **Given** docs/playbooks/pr-workflow.md, **When** read, **Then** it documents the required GitHub ruleset (required check on integration, protected-branch restriction, auto-merge + auto-delete-head). **Given** the consumer-fixture pr-mode end-to-end test, **When** CI is green (post-513), **Then** it passes.

## Work Log
