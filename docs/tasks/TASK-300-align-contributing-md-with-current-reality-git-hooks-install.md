---
id: TASK-300
title: "Align CONTRIBUTING.md with current reality: git-hooks install, task-id namespace scheme, commit limits, agent pr-mode"
swimlane: core
kind: docs
epic: panel-state-isolation
labels: [contributor, onboarding, ready]
status: complete
priority: P2
appetite: 1d
created: 2026-06-09
started: 2026-06-09
completed: 2026-06-09
agent_session: ses-claude-20260609-151118-a8c3
depends_on: []
blocked_by: []
references: []
---
# TASK-300: Align CONTRIBUTING.md with current reality: git-hooks install, task-id namespace scheme, commit limits, agent pr-mode

**Outcome (one sentence):** CONTRIBUTING.md tells contributors to install git hooks, set a task-id namespace to avoid id collisions, follow the real commit limits (≤100 title, ≤3 body lines, optional TASK-NNN ref), and set COS_GIT_WORKFLOW=pr for agent-driven branch work.

## Read First
- CONTRIBUTING.md
- src/scripts/install-git-hooks.sh
- docs/governance/task-lifecycle.md
- src/core/rules/git-workflow.md

## Work Log
- 2026-06-09 [claude]: Aligned CONTRIBUTING.md with current reality: added install-git-hooks.sh step (prepare-commit-msg task-id stamp + commit
