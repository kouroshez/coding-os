---
id: TASK-760
title: "memory-v2 P2: promotion ladder - /retro drafts rule or skill edits from Trusted lessons via cos_promote"
swimlane: core
kind: feature
epic: memory-v2
labels: [memory, ready]
status: icebox
priority: P2
appetite: 1d
created: 2026-07-02
started: null
completed: null
agent_session: null
depends_on: [TASK-759]
blocked_by: []
references: []
---

# TASK-760: memory-v2 P2: promotion ladder - /retro drafts rule or skill edits from Trusted lessons via cos_promote

**Outcome (one sentence):** Trusted lessons (conf>=0.7, >=3 validations) surface as human-approved promotion drafts in /retro through the existing cos_promote path; promoted lessons set promoted_to and leave the digest, and auto-validate measures recurrence-after-surface instead of raw substring match.

## Read First
- docs/engineering/learning-extraction.md
- src/core/rules/memory.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a Trusted lesson not yet promoted, **When** /retro runs, **Then** it lists the lesson with a draft rule/skill diff and applies nothing without human approval
- **Given** a promoted lesson, **When** the digest regenerates, **Then** the lesson no longer appears in Active Beliefs
- **Given** a surfaced lesson whose failure does not recur in-session, **When** task-done fires, **Then** learn_validate records was_helpful=true via the recurrence check

## Work Log
