---
id: TASK-589
title: "Validate git multi-agent system across 10+ real-world project use cases + document layered-defense model & pre-publish setup"
swimlane: core
kind: docs
epic: git-foundation-hardening
labels: [git, use-cases, validation, layered-defense, ready]
status: complete
priority: P2
appetite: 1d
created: 2026-06-26
started: 2026-06-26
completed: 2026-06-26
agent_session: ses-claude-20260625-235014-c028
depends_on: []
blocked_by: []
references: []
---
# TASK-589: Validate git multi-agent system across 10+ real-world project use cases + document layered-defense model & pre-publish setup

**Outcome (one sentence):** Prove the hardened git system works in the real world and make the model legible: a validated use-case matrix (≥10 project archetypes) showing recommended mode + expected behavior + any breakpoint, plus a doc capturing the Layer-0/1/2/3 layered-defense model (server-side branch protection = authoritative wall; client hooks = fast feedback) and the pre-publish GitHub setup checklist.

## Read First
- docs/playbooks/pr-workflow.md
- docs/architecture/adr/0013-pr-mode-multi-agent-git-workflow-consumer-only.md

## Work Log
- 2026-06-26 [claude]: Edit multi-agent-git-use-cases.md
- 2026-06-26 [claude]: commit 0893477134 — docs(playbook): add multi-agent git layered-defense model + 11 real-world use-case matrix
- 2026-06-26 [claude]: Wrote docs/playbooks/multi-agent-git-use-cases.md: the L0-L3 layered-defense model (server ruleset = authoritative…
