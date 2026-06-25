---
id: TASK-569
title: "Conditional: narrow TASK-NNN-only PostToolUse provenance nudge (build ONLY if comment-spam recurs after TASK-568)"
swimlane: core
kind: feature
epic: null
labels: [hooks, comments, discipline, deferred, conditional]
status: icebox
priority: P3
appetite: 1d
created: 2026-06-25
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-569: Conditional: narrow TASK-NNN-only PostToolUse provenance nudge (build ONLY if comment-spam recurs after TASK-568)

**Outcome (one sentence):** IF comment-provenance spam recurs after TASK-568's always-on context fix, add a NARROW PostToolUse Write|Edit nudge (non-blocking, fail-open, throttle once/file/session) that flags ONLY bare `TASK-NNN` tokens in strict comment context on added lines. NEVER a BLOCK and NEVER the full forbidden-token set: red-team (TASK-568 diagnosis) proved it is not zero-FP — gate codes (B3)/(G9) have 18 live legit src/core instances colliding with the (F-number) formula carve-out, and bare TASK-NNN still carries 70-90% semantic FP (legit-WHY + stray-id), so a block destroys good comments and contradicts block-bad-patterns.sh:104. Scope to code extensions, skip .md/docs/tasks, quote-parity guard for '#'-in-string fixtures. Reuses the existing warn-* PostToolUse precedent (registry.yaml). Trigger = a measured second/third recurrence, not speculative.

## Read First
- src/core/hooks/registry.yaml
- src/core/skills/clean-code/SKILL.md
- src/core/hooks/block-bad-patterns.sh

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a recurrence of provenance comments is observed after TASK-568, **When** the nudge hook runs on a Write/Edit adding `# ... TASK-123 ...`, **Then** it emits one throttled stderr line citing clean-code §4 and exits 0 (never blocks).
- **Given** an added comment with a formula id `(F1)` or a gate code `(B3)`, **When** the hook runs, **Then** it does NOT fire (carve-outs honored).
- **Given** no recurrence is measured, **Then** this task stays closed-unbuilt (convention-only remains correct per TASK-537).

## Work Log
