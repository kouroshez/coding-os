---
id: TASK-1135
title: "refactor(rules): one owner per rule \u2014 bodies to skills, one pointer line in AGENTS.md, no .codex/rules"
swimlane: infra
kind: refactor
epic: null
labels: [ready]
status: icebox
priority: P1
appetite: 2d
created: 2026-11-26
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-1135: refactor(rules): one owner per rule — bodies to skills, one pointer line in AGENTS.md, no .codex/rules

**Outcome (one sentence):** Each rule is stated in exactly one file and reaches both agents; findings C2, D2, D3 of the [audit § Duplication](../engineering/harness-loading-audit-2026-11.md#duplication-single-source) and L1, L2, L3 of [§ Claude loading](../engineering/harness-loading-audit-2026-11.md#claude-loading) are closed with a measured before/after token count per profile.

**Starts after TASK-1136:** L1's re-render is only correct once refresh_stack_rules uses D1's hash baseline.

## Read First
- docs/engineering/harness-loading-audit-2026-11.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a baseline taken with `cos doctor --tokens` in META and a fresh scaffold at task start, **When** it is re-run at close, **Then** always-on text is lower in both and no rule body appears in two always-on files.
- **Given** Codex in a scaffold, **When** `codex debug prompt-input` runs, **Then** every rule is reachable as a skill or an AGENTS.md line, and no .codex/rules dir exists.
- **Given** a META Claude session, **When** skills are listed, **Then** none come from tests/golden.

## Work Log
