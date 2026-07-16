---
id: TASK-319
title: "Agent-side auto-routing parity (CLI/VSCode, no hub UI) \u2014 rules+hooks surface the routing decision when toggle on"
swimlane: core
kind: feature
epic: null
labels: [model-routing, hooks, adapter-parity, audit-2026-06-09, ready]
status: archive
priority: P2
appetite: 1d
created: 2026-06-10
started: 2026-06-10
completed: 2026-06-10
agent_session: ses-claude-20260527-151803-0b9f
depends_on: [TASK-317, TASK-308]
blocked_by: []
references: []
---
# TASK-319: Agent-side auto-routing parity (CLI/VSCode, no hub UI) — rules+hooks surface the routing decision when toggle on

**Outcome (one sentence):** Any adapter session (Claude Code CLI, VSCode plugin, codex, …) with model_routing.enabled gets auto-routing without panel UI: a UserPromptSubmit-phase hook injects the routing directive (consult cos_route_model at Classify, honor it at dispatch) only when the toggle is on; the rule text lives in src/core/rules so every adapter inherits it; toggle off = zero injected tokens.

## Read First
- src/core/hooks/session-context.sh (existing additionalContext injection point)
- src/core/hooks/registry.yaml (hook registration SSOT — Rule 10 regen pipeline)
- src/core/rules/thinking_os.md (where the routing directive plugs into the Core Loop)
- src/core/thinking_os/tools/routing.py (cos_route_model)
- docs/tasks pointer: TASK-317 (settings SSOT this consumes)

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** model_routing.enabled=false
- **When** any prompt is submitted in a CLI/VSCode session
- **Then** no routing directive is injected (zero token cost, hook exits silently)
- **Given** enabled=true
- **When** a prompt is submitted
- **Then** the hook injects the directive once (debounced per session), the agent calls cos_route_model during Classify, and the chosen model reaches dispatch via the TASK-308 path
- **Given** adapter capability filtering
- **When** templates regenerate (make regen-adapter-templates)
- **Then** the hook lands only on adapters whose runtime fires UserPromptSubmit, per adapter.yaml — no hand-edits to derived artifacts

## Work Log
- 2026-06-10 [claude]: Shipped (score 9/10): nudge-model-routing.sh (UserPromptSubmit, fail-open, once-per-session marker, jq-reads hub-setting
- 2026-06-10 [claude]: committed 9033646e: src/adapters/claude/settings.template.json, src/adapters/cursor/hooks.cursor.template.json, src/core
- 2026-06-10 [claude]: Status transitioned to complete via cos task-done.
