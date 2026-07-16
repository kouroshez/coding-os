---
id: TASK-078
title: "release: stamp coding-os core version into consumer projects (cos init/update) — D6 silent-break risk"
swimlane: cli
kind: chore
epic: null
labels: []
status: archive
priority: P2
appetite: "1d"
created: 2026-06-04
started: 2026-06-04
completed: 2026-06-04
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-078: release: stamp coding-os core version into consumer projects (cos init/update) — D6 silent-break risk

**Outcome (one sentence):** Consumer projects pin to meta-repo core via live symlinks with no version stamp; a breaking hook/MCP change breaks them silently on cos update. Stamp the core version (e.g. .coding-os/core-version) at cos init/update so consumers know their core version and cos doctor can warn on incompatible core drift.

## Work Log
- 2026-06-04 [claude]: Status transitioned to complete via cos task-done.
