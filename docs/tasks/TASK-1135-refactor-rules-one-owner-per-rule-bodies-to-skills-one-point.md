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

**Outcome (one sentence):** Each rule is stated in exactly one file and reaches both agents; findings C2, D2, D3, L1, L2 and L3 of docs/engineering/harness-loading-audit-2026-11.md are closed with a measured before/after token count per profile.

## Read First
- docs/engineering/harness-loading-audit-2026-11.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a fresh scaffold and META, **When** `cos doctor --tokens` runs, **Then** always-on text is lower than the audit baseline and no rule body appears in two always-on files.
- **Given** Codex in a scaffold, **When** `codex debug prompt-input` runs, **Then** every rule is reachable as a skill or an AGENTS.md line, and no .codex/rules dir exists.
- **Given** a META Claude session, **When** skills are listed, **Then** none come from tests/golden.

## Work Log
