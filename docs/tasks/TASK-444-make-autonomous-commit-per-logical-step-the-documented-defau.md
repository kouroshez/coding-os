---
id: TASK-444
title: "Make autonomous commit-per-logical-step the documented default (override runtime \"commit only when asked\")"
swimlane: core
kind: docs
epic: null
labels: [governance, docs-update, git-workflow, ready]
status: archive
priority: P2
appetite: 1d
created: 2026-06-17
started: 2026-06-17
completed: 2026-06-17
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-444: Make autonomous commit-per-logical-step the documented default (override runtime "commit only when asked")

**Outcome (one sentence):** Agents commit their own work autonomously after each logical unit (no waiting to be asked) so an abandoned/mid-work session never leaves uncommitted files and review always has a committed diff to act on. Push stays gated (task-close / user ask) because src/core/** propagates to every consumer via live symlinks. Self-review (re-read own diff + matrix tests) is required before commit, but authoritative review stays a separate pass (reviewer role / /code-review / CI), never self-approval. The runtime "commit only when the user asks" default is explicitly OVERRIDDEN in the git-workflow SSOT and the change propagates to consumers + golden fixtures.

## Read First
- src/core/rules/git-workflow.md
- docs/governance/critical-rules.md
- src/core/skills/task-driver/SKILL.md
- AGENTS.md

## Work Log
- 2026-06-17 [claude]: Edit git-workflow.md
- 2026-06-17 [claude]: Edit critical-rules.md
- 2026-06-17 [claude]: Edit AGENTS.md
- 2026-06-17 [claude]: Edit SKILL.md
- 2026-06-17 [claude]: Edit SKILL.md
- 2026-06-17 [claude]: Edit SKILL.md
- 2026-06-17 [claude]: Edit agent-workflow.md
- 2026-06-17 [claude]: commit ab8d300438 — docs(workflow): commit per logical step autonomously by default (override "commit when asked")
- 2026-06-17 [claude]: Status transitioned to complete via cos task-done.
