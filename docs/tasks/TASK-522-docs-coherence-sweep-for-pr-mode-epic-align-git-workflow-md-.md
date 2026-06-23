---
id: TASK-522
title: "Docs-coherence sweep for pr-mode epic: align git-workflow.md, critical-rules 21/23, state-files, hub-architecture, AGENTS matrix"
swimlane: core
kind: docs
epic: multi-agent-pr-mode
labels: [pr-mode, docs-update, governance, ready]
status: complete
priority: P2
appetite: 1d
created: 2026-06-23
started: 2026-06-23
completed: 2026-06-23
agent_session: ses-claude-20260622-134704-4de9
depends_on: [TASK-519, TASK-520, TASK-521]
blocked_by: []
references: []
---
# TASK-522: Docs-coherence sweep for pr-mode epic: align git-workflow.md, critical-rules 21/23, state-files, hub-architecture, AGENTS matrix

**Outcome (one sentence):** After all pr-mode code lands, every doc touching git/worktree/multi-agent is mutually consistent — zero drift. git-workflow.md publish-mode seam fully specifies BOTH trunk and pr; critical-rules.md Rule 21 distinguishes the banned Agent-tool worktree-isolation from git-worktree-as-pr-workspace AND Rule 23 forward-refs the playbook; state-files.md gains the pr-mode×worktree state-routing row; hub-architecture.md lists git_settings + the Config→Git sub-tab; AGENTS.md Tool Routing + Verification Matrix mention `cos pr`; and docs/playbooks/pr-workflow.md (P0) matches the shipped code. Per-task doc edits happen inside each impl task (Rule 0/19); THIS task is the final cross-doc consistency pass so no two docs describe the same mechanic differently.

## Read First
- src/core/rules/git-workflow.md
- docs/governance/critical-rules.md
- docs/engineering/state-files.md
- docs/engineering/hub-architecture.md
- docs/playbooks/pr-workflow.md

## Work Log
- 2026-06-23 [claude]: Edit critical-rules.md
- 2026-06-23 [claude]: Edit critical-rules.md
- 2026-06-23 [claude]: Edit critical-rules.md
- 2026-06-23 [claude]: Edit state-files.md
- 2026-06-23 [claude]: Edit git-workflow.md
- 2026-06-23 [claude]: Edit AGENTS.md
- 2026-06-23 [claude]: commit 8d437b2d1a — docs(pr-mode): coherence sweep — git-workflow, critical-rules 21/23, state-files, AGENTS
- 2026-06-23 [claude]: Cross-doc coherence pass: critical-rules.md Rule 21 now explicitly distinguishes the banned Agent-tool…
