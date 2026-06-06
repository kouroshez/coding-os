---
id: TASK-082
title: "Merge 4 UserPromptSubmit nudge hooks into one dispatcher to cut per-prompt subprocess + stdin re-parse"
swimlane: infra
kind: refactor
epic: null
labels: [hooks, performance, deferred-from-TASK-080]
status: archive
priority: P3
appetite: "1d"
created: 2026-06-04
started: null
completed: null
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-082: Merge 4 UserPromptSubmit nudge hooks into one dispatcher to cut per-prompt subprocess + stdin re-parse

**Outcome (one sentence):** nudge-graph-os, nudge-task-discovery, nudge-docs-first, nudge-thinking-os each parse the same prompt stdin separately on every UserPromptSubmit. Merge into one nudge-dispatch that reads stdin once. Deferred from TASK-080 (low ROI — already per-session debounced; refactor risk). Also fold the 3 exhaustive-intent Write|Edit gates similarly.

## Read First
- (no doc yet — exploratory)

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** ...
- **When** ...
- **Then** ...

## Work Log
- 2026-06-06 [claude]: ARCHIVED (not done) — anti-overengineering (Rule 22). The card itself flags this as low-ROI: the 4 UserPromptSubmit nudg
