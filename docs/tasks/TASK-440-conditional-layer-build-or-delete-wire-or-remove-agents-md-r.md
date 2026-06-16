---
id: TASK-440
title: "Conditional layer build-or-delete: wire (or remove) AGENTS.md requires: + skill/hook overrides, render per-consumer rules, hide no-op design module + orphan goldens"
swimlane: infra
kind: refactor
epic: null
labels: [modularity, build-or-delete, conditional-assembly, audit-2026-06, ready]
status: icebox
priority: P1
appetite: 1d
created: 2026-06-16
started: null
completed: null
agent_session: null
depends_on: [TASK-438]
blocked_by: []
references: []
---

# TASK-440: Conditional layer build-or-delete: wire (or remove) AGENTS.md requires: + skill/hook overrides, render per-consumer rules, hide no-op design module + orphan goldens

**Outcome (one sentence):** Every declared-but-dead modularity mechanism is either made real or deleted (no half-wired surface a future contributor builds atop). Disabling a module/skill has the effect the Hub UI advertises, a consumer's Classify Read List points only at its own stacks, and zero-effect toggles disappear from the UI. Closes audit R6+R7+R8 + safe parts of R13 (problem-tree Branch B + Branch E).

## Read First
- src/cli/renderer.py
- src/templates/_base
- src/cli/project_overrides.py
- src/core/subsystems.yaml
- src/core/web/ui/src/pages/ConfigPage.tsx

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** a module disabled via CLI/Hub **When** AGENTS.md is regenerated **Then** the module's sections actually drop (base.yaml requires: rows wired + golden updated) OR the requires: field + renderer skip + empty rules:[] are deleted as speculative — one binary decision, documented.

**Given** the documented "disable a skill / disable a hook" capability **When** a user invokes it **Then** a writer persists skill-overrides.json/hook-overrides.json AND re-runs the adapter apply step in the same call OR the dead readers (load_skill_overrides, per-hook override branch) are removed and docs state hooks disable only via their owning module.

**Given** a python-only consumer **When** it reads its skill-enforcement.md / dimension-registry.md **Then** only its own stacks appear (rendered per-consumer at init/add/remove-stack, not symlinked all-stacks).

**Given** the no-op `design` module and 4 orphan golden dirs **When** the Hub Config tab / golden suite loads **Then** the design toggle is hidden until it owns an artifact and the orphan goldens are wired or deleted.

**Given** these changes **When** the matrix tests + golden parity run **Then** they pass.

## Work Log
