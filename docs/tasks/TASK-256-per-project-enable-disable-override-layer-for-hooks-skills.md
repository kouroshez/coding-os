---
id: TASK-256
title: "Per-project enable/disable override layer for hooks+skills"
swimlane: core
kind: feature
epic: kernel-overrides
labels: [ready]
status: complete
priority: P2
appetite: 3d
created: 2026-06-08
started: 2026-06-08
completed: 2026-06-08
agent_session: ses-claude-20260608-024900-f2b0
depends_on: []
blocked_by: []
references: []
---
# TASK-256: Per-project enable/disable override layer for hooks+skills

**Outcome (one sentence):** Add per-project .coding-os/{hook,skill}-overrides.json honored at render and runtime (safety hooks non-disableable) to enable Config toggles.

## Read First
- src/core/hooks/registry.yaml — the GLOBAL hook SSOT (must NEVER be edited per-project — a Hub toggle there de-armours every consumer).
- src/cli/hook_renderer.py — render-time hook selection (must skip disabled).
- src/core/hooks/cos-env.sh — runtime hook dispatch (must honor the override).

## Context / Approach
A NEW per-project governance primitive: .coding-os/{hook,skill}-overrides.json honored at BOTH render time (hook_renderer skips disabled) and runtime (cos-env.sh / dispatch reads it). Safety-category hooks are NON-disableable (greyed in the Config UI). This unblocks the Config page toggles WITHOUT editing the global registry. XL — touches the kernel/hook layer that propagates to all consumers.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a disabled non-safety hook in the override, **When** rendering/running, **Then** it does not fire for that project.
- **Given** a safety-category hook, **When** a disable is attempted, **Then** it is refused.

## Work Log
- 2026-06-08 [claude]: Added cli.project_overrides (safety-category hooks non-disableable, derived disabled-hook-scripts allowlist) + cos-env.s
