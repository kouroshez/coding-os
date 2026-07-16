---
id: TASK-421
title: "Wire module toggles (docs/tasks/graph/memory) into the new-project Composer + cos init"
swimlane: core
kind: feature
epic: null
labels: [hub, onboarding, modules, ready]
status: archive
priority: P1
appetite: 1d
created: 2026-06-15
started: 2026-06-15
completed: 2026-06-15
agent_session: ses-claude-20260615-014142-5969
depends_on: []
blocked_by: []
references: []
---
# TASK-421: Wire module toggles (docs/tasks/graph/memory) into the new-project Composer + cos init

**Outcome (one sentence):** Let a user enable/disable subsystem modules (docs, tasks, graph, memory, design; kernel locked, tasks->docs dependency respected) at project-creation time from the Composer's Advanced section, instead of only post-create in Config. Split out of TASK-419, which shipped the Composer but deferred module-at-create because it needs a new surface: a `cos init` module flag + scaffold wiring + a Hub module-catalog endpoint.

## Read First
- src/core/web/ui/src/pages/OnboardingWizard.tsx — Composer Advanced section to extend
- src/core/web/routes/hub.py — init/validate-init + a new module-catalog endpoint
- src/cli/main.py — `cos init` (add a module flag mirroring preset.modules)
- src/core/subsystems.yaml — the module catalog (docs/tasks/graph/memory/design + kernel)
- src/cli/subsystems.py — set_module_enabled + dependency validation
- src/core/web/ui/src/pages/ConfigPage.tsx — the post-create module toggle UI to mirror

## Acceptance (G/W/T) — *this IS the Definition of Done*

### 1 Module catalog endpoint
- **Given** the Composer Advanced section
- **When** it renders
- **Then** a new GET /api/hub/modules (reading src/core/subsystems.yaml) supplies the non-kernel modules, shown as toggles defaulting to enabled, with the tasks->docs dependency enforced in the UI

### 2 Modules wired into create
- **Given** a user disables a module and creates the project
- **When** POST /api/hub/registry/init runs
- **Then** it accepts a disabled-modules param, passes it to `cos init` via a new flag mirroring preset.modules, and the scaffolded project's subsystems-state.json reflects the choice

### 3 Verify
- **Given** the change is complete
- **When** closing
- **Then** tests cover the endpoint + init wiring (tests/test_hub_init_route.py, tests/test_cli.py) and the Composer toggle (OnboardingWizard.test.tsx); hub-architecture.md notes the module-at-create flow

## Work Log
- 2026-06-15 [claude]: Split out of TASK-419 (Composer shipped). Module-at-create deferred there because it needs a new `cos init` flag + scaffold wiring + a Hub module-catalog endpoint — distinct from the UI redesign.
- 2026-06-15 [claude]: Edit main.py
- 2026-06-15 [claude]: Edit main.py
- 2026-06-15 [claude]: Edit main.py
- 2026-06-15 [claude]: Edit main.py
- 2026-06-15 [claude]: Edit main.py
- 2026-06-15 [claude]: Edit test_cli.py
- 2026-06-15 [claude]: Edit hub.py
- 2026-06-15 [claude]: Edit hub.py
- 2026-06-15 [claude]: Edit hub.py
- 2026-06-15 [claude]: Edit hub.py
- 2026-06-15 [claude]: Edit hub.py
- 2026-06-15 [claude]: Edit hub.py
- 2026-06-15 [claude]: Edit hub.py
- 2026-06-15 [claude]: Edit hub.py
- 2026-06-15 [claude]: Edit hub.py
- 2026-06-15 [claude]: Edit hub.py
- 2026-06-15 [claude]: Edit hub.py
- 2026-06-15 [claude]: Edit hub.py
- 2026-06-15 [claude]: Edit hub.py
- 2026-06-15 [claude]: Edit test_hub_init_route.py
- 2026-06-15 [claude]: Edit test_hub_init_route.py
- 2026-06-15 [claude]: Edit OnboardingWizard.tsx
- 2026-06-15 [claude]: Edit OnboardingWizard.tsx
- 2026-06-15 [claude]: Edit OnboardingWizard.tsx
- 2026-06-15 [claude]: Edit OnboardingWizard.tsx
- 2026-06-15 [claude]: Edit OnboardingWizard.tsx
- 2026-06-15 [claude]: Edit OnboardingWizard.tsx
- 2026-06-15 [claude]: Edit OnboardingWizard.tsx
- 2026-06-15 [claude]: Edit OnboardingWizard.tsx
- 2026-06-15 [claude]: Edit OnboardingWizard.tsx
- 2026-06-15 [claude]: Edit OnboardingWizard.test.tsx
- 2026-06-15 [claude]: Edit OnboardingWizard.test.tsx
- 2026-06-15 [claude]: Edit hub-architecture.md
- 2026-06-15 [claude]: Edit 0009-new-project-composer.md
- 2026-06-15 [claude]: commit 9f00400566 — feat(hub): choose active modules at create (--disable-module, /api/hub/modules, Composer) TASK-421
- 2026-06-15 [claude]: Done (commit 9f004005). Module selection at create wired end-to-end. CLI: `cos init --disable-module <id>` (repeatable)
- 2026-06-15 [claude]: Status transitioned to complete via cos task-done.
