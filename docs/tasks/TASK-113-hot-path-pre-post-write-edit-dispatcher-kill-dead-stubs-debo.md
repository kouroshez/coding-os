---
id: TASK-113
title: "Hot-path Pre/Post Write|Edit dispatcher + kill dead stubs + debounce test-first + fix auto-regen-doc-index dead path"
swimlane: core
kind: refactor
epic: hook-remediation
labels: [hooks, performance, dispatcher, audit-n9]
status: icebox
priority: P2
appetite: "1d"
created: 2026-06-05
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-113: Hot-path Pre/Post Write|Edit dispatcher + kill dead stubs + debounce test-first + fix auto-regen-doc-index dead path

**Outcome (one sentence):** Single PreToolUse and single PostToolUse Write|Edit dispatcher parse stdin once and fan out in-process (cuts ~42 spawns/edit); dead stubs (verify-changed-file, doc-sync-reminder) deleted + regen; test-first-reminder debounced (no 6k-file find per edit); auto-regen-doc-index resolves src/scripts path.

## Read First
- src/core/hooks/registry.yaml
- src/cli/hook_renderer.py
- src/core/hooks/test-first-reminder.sh
- src/core/hooks/auto-regen-doc-index.sh

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** ...
- **When** ...
- **Then** ...

## Work Log
