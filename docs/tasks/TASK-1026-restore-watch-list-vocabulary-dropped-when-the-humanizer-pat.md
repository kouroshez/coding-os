---
id: TASK-1026
title: "Restore watch-list vocabulary dropped when the humanizer patterns were compressed"
swimlane: core
kind: bug
epic: null
labels: [governance, skills, ready]
status: in_progress
priority: P2
appetite: 1d
created: 2026-08-24
started: 2026-08-24
completed: null
agent_session: ses-claude-20260820-192937-ef87
depends_on: []
blocked_by: []
references: []
---
# TASK-1026: Restore watch-list vocabulary dropped when the humanizer patterns were compressed

**Outcome (one sentence):** Every detection phrase the upstream skill names survives in the vendored catalogue, so no pattern loses the vocabulary that lets an agent recognise it.

## Read First
- src/core/skills/humanizer/references/patterns.md
- src/core/skills/humanizer/SKILL.md

## Repro Steps
Run scratchpad/audit_humanizer.py against the upstream SKILL.md: 26 of 130 watch tokens report missing. Filtering the normaliser's false positives (slash-separated alternates such as "serves as/stands as" match fine), these are genuinely absent from references/patterns.md: focal point, contributing to the, marking/shaping the, encompassing, cultivating, local/regional media outlets, several sources, scarce, keeps personal details private, began, this is an inference, before I forget, Some would suggest, trying to, frame this differently, significant/moment.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the upstream watch lines for patterns 1 through 35
  **When** the vendored catalogue is compared token by token
  **Then** every upstream detection phrase is present, allowing for slash-separated alternates being spelled out.
- **Given** the audit script with its label-matching assertion corrected
  **When** it runs against the upstream file
  **Then** all checks pass.

## Work Log
- 2026-08-24 [claude]: Edit patterns.md
