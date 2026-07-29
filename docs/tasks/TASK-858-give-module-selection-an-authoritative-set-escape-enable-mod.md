---
id: TASK-858
title: "Give module selection an authoritative-set escape (--enable-module / --modules-exact)"
swimlane: core
kind: feature
epic: null
labels: [cli, modules, profiles, review-followup, ready]
status: icebox
priority: P2
appetite: 1d
created: 2026-07-29
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-858: Give module selection an authoritative-set escape (--enable-module / --modules-exact)

**Outcome (one sentence):** A caller can state the exact module set it wants without knowing that profile and `--disable-module` are unioned.

## Read First
- src/core/subsystems.yaml
- src/cli/main.py
- docs/engineering/hub-architecture.md

## Context
`cos init` unions the profile's disabled set with every `--disable-module`, so a profile can only ever remove more. Re-enabling something a profile turned off requires starting from a wider profile — a workaround every consumer must rediscover. The Hub route already encodes it (pins the widest profile, sends the complete set); `cos adopt`, the agent recipe, and any future MCP/CI caller each have to repeat it or silently ship a leaner project than requested.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a profile that disables `cognition`, **When** the caller asks for it explicitly, **Then** the created project has `cognition` enabled.
- **Given** the new flag, **When** the Hub init route uses it, **Then** the route no longer needs to pin a profile to make its payload authoritative.
- **Given** the CLI help, **When** a user reads it, **Then** the union semantics and the escape are both stated.

## Work Log
