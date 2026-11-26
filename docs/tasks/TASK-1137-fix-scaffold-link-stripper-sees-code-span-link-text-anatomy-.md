---
id: TASK-1137
title: "fix(scaffold): link stripper sees code-span link text; anatomy links the consumer boundary file; CI lints rendered stacks"
swimlane: infra
kind: bug
epic: null
labels: [ready]
status: icebox
priority: P2
appetite: 1d
created: 2026-11-26
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-1137: fix(scaffold): link stripper sees code-span link text; anatomy links the consumer boundary file; CI lints rendered stacks

**Outcome (one sentence):** No rendered stack ships a dangling link; findings K1 and K2 of the [audit § Links](../engineering/harness-loading-audit-2026-11.md#links) are closed.

## Read First
- docs/engineering/harness-loading-audit-2026-11.md
- src/cli/_localize_links.py

## Repro Steps
In a fresh fastapi scaffold, .agents/skills/python-fastapi/references/anatomy.md:15 links ../../../scaffold-boundary.yaml, which does not exist (audit K1).

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** every stack rendered into a temp dir, **When** `cos doc-lint` runs in each, **Then** it reports no broken link.
- **Given** a link whose text is a code span and whose target is missing, **When** localization runs, **Then** the link is unlinked.

## Work Log
