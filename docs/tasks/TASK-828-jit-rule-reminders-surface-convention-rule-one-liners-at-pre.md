---
id: TASK-828
title: "JIT rule reminders \u2014 surface convention-rule one-liners at PreToolUse edit time via jit-recall glob map"
swimlane: core
kind: feature
epic: null
labels: [context-economy, hooks, ready]
status: archive
priority: P1
appetite: 1d
created: 2026-07-16
started: 2026-07-16
completed: 2026-07-16
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-828: JIT rule reminders — surface convention-rule one-liners at PreToolUse edit time via jit-recall glob map

**Outcome (one sentence):** Convention-only rules (api-contract-discipline first) drift because they are injected at token 0 and forgotten by edit time. Extend the existing jit-recall hook with a static glob-to-message map (jit-rules.tsv) so a one-line rule reminder reaches the agent at the exact moment it edits a matching file — warn-only, debounced once per rule per session, zero new hook registration.

## Read First
- src/core/hooks/jit-recall.sh
- src/core/hooks/registry.yaml
- docs/engineering/hooks-reference.md
- src/core/rules/api-contract-discipline.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** a Write/Edit on a path matching a jit-rules.tsv glob, **When** jit-recall fires, **Then** the mapped rule one-liner is emitted to stderr exactly once per session (marker debounce) and exit code stays 0. **Given** a non-matching path or a repeated edit, **When** the hook fires, **Then** no rule line is emitted. **Given** make verify-hooks and the new behavior test, **When** run, **Then** both pass.

## Work Log
- 2026-07-16 [claude]: Extended jit-recall with jit-rules.tsv (glob→rule one-liners, warn-only, per-rule/session debounce in .jit-nudge/…
- 2026-07-16 [claude]: Status transitioned to complete via cos task-done.
