---
id: TASK-249
title: "Create-from-UI: init route + New Project wizard"
swimlane: core
kind: feature
epic: hub-redesign
labels: [ready]
status: archive
priority: P1
appetite: 3d
created: 2026-06-08
started: 2026-06-08
completed: 2026-06-08
agent_session: ses-claude-20260608-024900-f2b0
depends_on: []
blocked_by: []
references: []
---
# TASK-249: Create-from-UI: init route + New Project wizard

**Outcome (one sentence):** Let a user create a new project from the Hub UI (no CLI) via a security-gated init route and a New Project wizard.

## Read First
- src/cli/main.py — `init` (~923) + `_refuse_coding_os_self_init` (~826): scaffold machinery + self-init guard.
- src/core/web/routes/hub.py — hub-global routes + _validate_project_path + suggest-roots.
- src/core/web/ui/src/pages/HubHome.tsx — where the wizard + "+ New project" mount; reuse the Modal primitive.

## Context / Approach
POST /api/hub/registry/init on the UNSCOPED hub router (no slug yet — structurally hub-global). Run cli.main.init in a thread/subprocess with a timeout; run _refuse_coding_os_self_init; validate parent_dir against nesting; register ONLY on clean exit (a failed init leaves nothing). Add GET /api/hub/stacks for a data-driven stack grid (Rule 11). New Project wizard modal: location chips + name→slug + stack grid. Depends on TASK-248 (security gate).

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the wizard with a location + stack, **When** submitted, **Then** init scaffolds in a thread, registers on clean exit, and routes to the project.
- **Given** an init that fails midway, **When** it errors, **Then** nothing is registered.

## Work Log
- 2026-06-08 [claude]: Added GET /api/hub/stacks (data-driven) + security-gated POST /api/hub/registry/init (subprocess cos init, validates nam
