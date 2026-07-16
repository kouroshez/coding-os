---
id: TASK-076
title: "release: add RELEASE_PLEASE_TOKEN PAT so the standing release PR triggers CI before merge"
swimlane: infra
kind: chore
epic: null
labels: []
status: archive
priority: P2
appetite: "1d"
created: 2026-06-04
started: 2026-06-04
completed: 2026-06-04
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-076: release: add RELEASE_PLEASE_TOKEN PAT so the standing release PR triggers CI before merge

**Outcome (one sentence):** Release PR is CI-validated. GITHUB_TOKEN-created PRs do not trigger downstream workflows; a fine-grained PAT (contents:RW + pull_requests:RW) as RELEASE_PLEASE_TOKEN secret fixes this and lets the release PR run the full CI gate before a human merges it.

## Work Log
- 2026-06-04 [claude]: Status transitioned to complete via cos task-done.
