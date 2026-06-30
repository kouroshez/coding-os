---
id: TASK-673
title: "Escalate CLEAR-1 self-bypass \u2014 count + surface repeated gate bypasses in retro (informational)"
swimlane: core
kind: feature
epic: hook-consolidation
labels: [hooks, clear1, retro, ready]
status: icebox
priority: P3
appetite: 1d
created: 2026-06-30
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-673: Escalate CLEAR-1 self-bypass — count + surface repeated gate bypasses in retro (informational)

**Outcome (one sentence):** Repeated CLEAR-1 self-bypasses (manual CLEAR 1 gate sets that skip doc-anchor/skill/task-start/memory-check enforcement) are counted and surfaced to retro with their recorded justifications from .clear1-bypass-log, so routing-around-the-discipline becomes a visible trend rather than a silent habit — informational only, never a new block.

## Read First
- src/core/rules/transparency-banner.md
- src/core/hooks/session-context.sh
- docs/governance/critical-rules.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** N self-issued CLEAR-1 bypasses in a session, **When** retro runs, **Then** the count and each recorded justification are surfaced from .clear1-bypass-log.
- **Given** the surfacing, **When** it is rendered, **Then** it is informational (ℹ️) and never a block or refusal.
- **Given** a session with zero bypasses, **When** retro runs, **Then** nothing is emitted for this signal.

## Work Log
