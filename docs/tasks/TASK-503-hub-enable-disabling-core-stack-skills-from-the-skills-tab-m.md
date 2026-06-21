---
id: TASK-503
title: "Hub: enable disabling core/stack skills from the Skills tab (modularity HUB-PB1)"
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
# TASK-503: Hub: enable disabling core/stack skills from the Skills tab (modularity HUB-PB1)

---
id: TASK-503
title: "Hub: enable disabling core/stack skills from the Skills tab (modularity HUB-PB1)"
swimlane: core
kind: feature
epic: null
labels: [ready]
status: icebox
priority: P2
appetite: 1d
created: 2026-06-21
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-503: Hub: enable disabling core/stack skills from the Skills tab (modularity HUB-PB1)

**Outcome (one sentence):** The Hub Skills tab can disable (not just add) a core/stack skill, reaching parity with cos skill disable via the set_project_skill the route already calls.

## Read First
- src/core/web/ui/src/pages/ConfigPage.tsx
- src/core/web/routes/config.py
- src/cli/skill_commands.py
- src/core/rules/api-contract-discipline.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** a project with a linked core/stack skill
**When** the operator clicks Disable in the Hub Skills tab
**Then** config_skills emits disabled+provenance (field names verified against the producer per api-contract-discipline), the PATCH sends {enabled:false} through the existing set_project_skill, the SKILL.md symlink is unlinked, the row shows Disabled, AND the all-modules-on render is unchanged.

## Work Log
- 2026-06-21 [claude]: config_skills now emits provenance+disabled (reads disabled_skills); SkillsTab branches core/stack → Enable/Disable…
- 2026-06-21 [claude]: Edit settings.py
- 2026-06-21 [claude]: Edit ConfigPage.tsx
- 2026-06-21 [claude]: Edit ConfigPage.tsx
- 2026-06-21 [claude]: Edit ConfigPage.tsx
- 2026-06-21 [claude]: Edit ConfigPage.tsx
