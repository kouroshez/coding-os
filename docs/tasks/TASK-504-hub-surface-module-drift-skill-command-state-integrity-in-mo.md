---
id: TASK-504
title: "Hub: surface module drift (skill/command/state_integrity) in ModulesTab (modularity HUB-PB2)"
swimlane: core
kind: feature
epic: null
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-06-21
started: 2026-06-21
completed: 2026-06-21
agent_session: ses-claude-20260620-223048-0760
depends_on: []
blocked_by: []
references: []
---
# TASK-504: Hub: surface module drift (skill/command/state_integrity) in ModulesTab (modularity HUB-PB2)

**Outcome (one sentence):** The Hub shows a WARN banner when modules.skill_drift / command_drift / state_integrity is non-PASS, so a Hub-driven toggle that strands a symlink or corrupts state is visible in the UI that performed it.

## Read First
- src/cli/doctor.py
- src/core/web/routes/settings.py
- src/core/web/ui/src/pages/ConfigPage.tsx
- src/cli/module_commands.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** a stranded module-owned skill symlink (or command/state-integrity drift) after a Hub toggle
**When** ModulesTab loads
**Then** a new read-only GET /api/settings/modules/drift returns the non-PASS check (reusing the three existing doctor check functions — no new check logic), AND a WARN banner renders, AND with no drift present the banner is absent.

## Work Log
- 2026-06-21 [claude]: Added GET /api/settings/modules/drift reusing the 3 cos doctor checks…
