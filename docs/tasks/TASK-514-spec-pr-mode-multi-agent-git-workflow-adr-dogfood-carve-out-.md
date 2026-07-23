---
id: TASK-514
title: "Spec PR-mode multi-agent git workflow: ADR (dogfood carve-out + Rule-21 distinction) + playbook"
swimlane: core
kind: docs
epic: multi-agent-pr-mode
labels: [pr-mode, governance, docs-update, ready]
status: archive
priority: P1
appetite: 1d
created: 2026-06-22
started: 2026-06-22
completed: 2026-06-22
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-514: Spec PR-mode multi-agent git workflow: ADR (dogfood carve-out + Rule-21 distinction) + playbook

**Outcome (one sentence):** A merged ADR + docs/playbooks/pr-workflow.md so every downstream pr-mode code change traces to a spec (Rule 0/19). The ADR resolves the P5 dogfood horn (coding-os stays trunk; pr-mode is consumer-only opt-in) and distinguishes the banned Agent-tool isolation:"worktree" (Rule 21) from git-worktree-as-pr-workspace. The playbook defines the corrected flow, naming/slug, preflight capability gate, orphan reaper, and bounded self-heal budget. Source spec: ~/Desktop/ci-cd/multi-agent-workflow-LEAN-2026-06-19.md.

## Read First
- src/core/rules/git-workflow.md
- docs/governance/critical-rules.md
- docs/engineering/state-files.md
- docs/engineering/hub-architecture.md

## Work Log
- 2026-06-23 [claude]: Edit 0013-pr-mode-multi-agent-git-workflow-consumer-only.md
- 2026-06-23 [claude]: Edit pr-workflow.md
- 2026-06-23 [claude]: commit 66a84af978 — docs(pr-mode): ADR-0013 + pr-workflow playbook for consumer-only pr-mode
- 2026-06-23 [claude]: Wrote ADR-0013 (consumer-only pr-mode; coding-os stays trunk) + docs/playbooks/pr-workflow.md (concrete spec for…
