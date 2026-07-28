---
id: TASK-619
title: "CI economics: ship a fast required-check + consumer CI workflow template + minute-budget guidance (Linux/public/self-hosted)"
swimlane: infra
kind: chore
epic: git-foundation-hardening
labels: [pr-mode, ci, cost, ready]
status: archive
priority: P2
appetite: 1d
created: 2026-06-27
started: 2026-06-27
completed: 2026-06-27
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-619: CI economics: ship a fast required-check + consumer CI workflow template + minute-budget guidance (Linux/public/self-hosted)

**Outcome (one sentence):** On a free private repo with a slow suite, auto_merge + merge-queue multiplies CI runs and burns the 2000-min/mo budget fast (macOS bills 10x), yet there is no consumer CI template and the recommended economics are undocumented — so a cost-sensitive consumer cannot adopt the autonomous loop safely. Ship a consumer CI workflow template (Linux runners only, a FAST required check = lint + targeted tests, merge_group trigger, full suite on a nightly cron) plus a budget-guidance doc (public repo = unlimited Actions, self-hosted runner = unlimited, the 10x macOS warning, fast-gate vs full-suite split). EXTERNAL part: the actual billing/runner choice is the consumer's call.

## Work Log
- 2026-06-28 [claude]: Shipped docs/playbooks/pr-mode-ci-economics.md: cost model (Linux x1/Win x2/macOS x10, private 2000min,…
