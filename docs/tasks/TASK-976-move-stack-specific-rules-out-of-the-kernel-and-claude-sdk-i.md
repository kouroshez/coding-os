---
id: TASK-976
title: "Move stack-specific rules out of the kernel and Claude SDK imports out of core"
swimlane: core
kind: refactor
epic: null
labels: [kernel, P2, P8, architecture, ready]
status: complete
priority: P1
appetite: 1d
created: 2026-08-14
started: 2026-08-14
completed: 2026-08-14
agent_session: ses-claude-20260814-120316-413b
depends_on: []
blocked_by: []
references: []
---
# TASK-976: Move stack-specific rules out of the kernel and Claude SDK imports out of core

**Outcome (one sentence):** The agent-agnostic, stack-agnostic kernel holds no Django opinions and no adapter SDK imports, so P2 and P8 hold in code and not only in the principles list.

## Read First
- src/core/hooks/block-bad-patterns.sh:226-239
- docs/engineering/adapter-parity.md
- pyproject.toml § dependencies

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a project on a non-Django stack, **When** it writes a `views.py`, **Then** no kernel hook rejects ORM usage on Django grounds.
- **Given** the Django stack overlay, **When** it is installed, **Then** those rules still fire.
- **Given** src/core/**, **When** it is grepped for adapter SDK imports, **Then** there are none; the Hub reaches a runtime through a port with a fake in tests.
- **Given** a fresh install without the claude extra, **When** the Hub starts, **Then** it runs and reports the missing runtime rather than failing to import.

## Work Log
- 2026-08-14 [claude]: Both halves done: 89e40f4c (stack rules) and 57771933 (P8). Correction to my own earlier report — only THREE core…
- 2026-08-14 [claude]: Status transitioned to complete via cos task-done.
