---
id: TASK-1089
title: "Consumers: propagate the cognition cut (cos sync-all + repair dangling hook links) to every registered project"
swimlane: infra
kind: chore
epic: null
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-10-25
started: 2026-10-25
completed: 2026-10-25
agent_session: ses-claude-20261024-131905-031f
depends_on: []
blocked_by: []
references: []
---
# TASK-1089: Consumers: propagate the cognition cut (cos sync-all + repair dangling hook links) to every registered project

**Outcome (one sentence):** Every project built with coding-os runs the current kernel: migration v55 applied, adapter settings re-rendered without the six removed hooks, and no dangling hook symlinks left.

## Read First
- docs/engineering/hub-architecture.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the registered projects (stream-os and the rest)
- **When** `cos sync-all` runs, followed by `cos sync-doctor --repair` where links dangle
- **Then** each project's `.claude/settings.json` / `.codex/hooks.json` names none of the removed hooks, `find .claude/hooks .codex/hooks -xtype l` is empty, the DB is at schema 55, and a synthetic hook run exits 0

## Work Log
- 2026-10-25 [claude]: cos sync-all per project (one at a time, nice): streamos, cos-website, trading-terminal all at schema v55; dangling…
- 2026-10-25 [claude]: Status transitioned to complete via cos task-done.
