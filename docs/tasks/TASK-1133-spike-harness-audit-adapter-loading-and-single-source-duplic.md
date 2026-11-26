---
id: TASK-1133
title: "spike(harness): audit adapter loading and single-source duplication against community practice"
swimlane: infra
kind: spike
epic: null
labels: [ready]
status: in_progress
priority: P1
appetite: 1d
created: 2026-11-26
started: 2026-11-26
completed: null
agent_session: ses-claude-20261125-165238-7b8d
depends_on: []
blocked_by: []
references: []
---
# TASK-1133: spike(harness): audit adapter loading and single-source duplication against community practice

**Outcome (one sentence):** One audit doc with a verified mind map and checklist for the six open items (Codex rules, templates mirror, anatomy link, consumer pre-commit helper, always-on token cost, cos run governor bypass) plus what each adapter really loads, each claim cited to file:line, a command run, or a source URL; fix tasks link to its sections.

## Read First
- src/adapters/codex/adapter.yaml
- src/adapters/claude/adapter.yaml
- docs/engineering/adapter-parity.md
- docs/engineering/project-anatomy.md
- src/core/rules/memory.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the audit doc, **When** a reader checks any finding, **Then** it cites a file:line, a command that was run, or a source URL.
- **Given** each of the six open items, **When** the doc is read, **Then** it states the current behaviour, the community practice found, and the chosen single-source fix.

## Work Log
