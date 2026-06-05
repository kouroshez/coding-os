---
id: TASK-155
title: "Data-driven agent detection in cos-env.sh — generate detection snippet from adapter.yaml runtime markers"
swimlane: core
kind: feature
epic: hook-remediation
labels: [hooks, adapter, data-driven, audit-n8-followup]
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

# TASK-155: Data-driven agent detection in cos-env.sh — generate detection snippet from adapter.yaml runtime markers

**Outcome (one sentence):** cos-env.sh agent-detection if/elif (and the panel session-marker loop + model-env resolver) is GENERATED at regen time from src/adapters/*/adapter.yaml::runtime_env_markers + runtime_session_marker, sourced as a pre-built _agent-detect.generated.sh so the hot path stays fast (no per-hook YAML parse) yet a new adapter (gemini/opencode) is picked up by editing only its adapter.yaml + running regen. Then extend tests/test_no_hardcoded_stacks.py to scan src/core/hooks/*.sh (8c) — it can only go green once cos-env's literals come from the generated file. Deferred from N8 because cos-env.sh is sourced by every hook of every adapter; the change needs a generator + regen wiring + byte-equivalence diff vs the current hardcoded logic + per-adapter detection smoke, out of the audit stream's safe blast radius.

## Read First
- src/core/hooks/cos-env.sh
- src/adapters/claude/adapter.yaml
- src/cli/board_commands.py
- tests/test_no_hardcoded_stacks.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** ...
- **When** ...
- **Then** ...

## Work Log
