---
id: TASK-636
title: "Add a lite/MCP-minimal install profile and a module-discovery UX in the Hub Config tab"
swimlane: core
kind: feature
epic: cognitive-kernel-hardening
labels: [distribution, hub, profiles, ux, ready]
status: archive
priority: P3
appetite: 1d
created: 2026-06-28
started: 2026-06-28
completed: 2026-06-28
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-636: Add a lite/MCP-minimal install profile and a module-discovery UX in the Hub Config tab

**Outcome (one sentence):** Widen adoption and discoverability without new machinery: a new `lite` profile in subsystems.yaml (discipline-only — rules+blocking hooks, near-zero MCP tool surface) for MCP-averse adopters, plus an enriched Hub Config Modules tab (per-module description + when-to-enable hint, card layout) so capabilities are discoverable and individually toggleable over the EXISTING module registry — no folder-per-plugin sprawl.

## Read First
- src/core/subsystems.yaml
- src/cli/subsystems.py
- src/cli/module_commands.py
- src/core/web/ui/src/pages/ConfigPage.tsx
- docs/engineering/hub-architecture.md
- src/core/skills/react-vite-hub/SKILL.md

## Implementation Notes (verified against source 2026-06-28)
Profiles live in subsystems.yaml (~lines 30-33: core/standard/full as `disabled:` lists; default_profile standard at line 29) — add `lite`. The Module dataclass is `src/cli/subsystems.py` (~31-43: id/label/kernel/hooks/tools/skills/commands/depends_on/hidden — no `hint`/`description` field). The serializer `module_state_payload()` is `src/cli/module_commands.py` (~251-271). The route is GET /modules in `src/core/web/routes/settings.py` (~155). The Hub ModulesTab is ConfigPage.tsx (~396-493), today a bare Table with no description/hint column.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the `lite` profile (selected via flag or state), **When** resolved, **Then** only kernel-owned cos_* tools survive and subsystems-state.json records the choice (machine-readable, unlike a one-shot shell prompt).
- **Given** the Hub Config -> Modules tab, **When** opened, **Then** each non-kernel module shows label+description+hint with an enable toggle, reusing the existing /api/settings/modules route (no new page/route).
- **Given** a `hint` field added to subsystems.yaml, **When** module_state_payload() serves it, **Then** the Module dataclass + payload are updated in the same commit (subsystems.yaml is hand-maintained SSOT, no regen).
- **Given** the cli and web suites, **When** run, **Then** green.

## Work Log
- 2026-06-28 [claude]: Edit subsystems.yaml
- 2026-06-28 [claude]: Edit subsystems.yaml
- 2026-06-28 [claude]: Edit subsystems.yaml
- 2026-06-28 [claude]: Edit subsystems.yaml
- 2026-06-28 [claude]: Edit subsystems.yaml
- 2026-06-28 [claude]: Edit subsystems.yaml
- 2026-06-28 [claude]: Edit subsystems.yaml
- 2026-06-28 [claude]: Edit subsystems.yaml
- 2026-06-28 [claude]: Edit subsystems.yaml
- 2026-06-28 [claude]: Edit subsystems.yaml
- 2026-06-28 [claude]: Edit subsystems.yaml
- 2026-06-28 [claude]: Edit subsystems.py
- 2026-06-28 [claude]: Edit subsystems.py
- 2026-06-28 [claude]: Edit module_commands.py
- 2026-06-28 [claude]: Edit ConfigPage.tsx
- 2026-06-28 [claude]: Edit ConfigPage.tsx
- 2026-06-28 [claude]: Edit test_cli.py
- 2026-06-28 [claude]: Edit ConfigPage.test.tsx
- 2026-06-28 [claude]: Edit ConfigPage.test.tsx
- 2026-06-28 [claude]: Edit commit636.txt
- 2026-06-28 [claude]: Shipped both parts over the existing module registry (no folder-per-plugin sprawl). (A) `lite` profile in…
- 2026-06-28 [claude]: Status transitioned to complete via cos task-done.
