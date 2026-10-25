---
id: TASK-1081
title: "Hub: remove the Roles view; split Skills and MCP Servers into project vs global scope"
swimlane: core
kind: feature
epic: null
labels: [docs-update, hub, ready]
status: in_progress
priority: P2
appetite: 1d
created: 2026-10-25
started: 2026-10-25
completed: null
agent_session: ses-claude-20261024-131905-031f
depends_on: []
blocked_by: []
references: []
---
# TASK-1081: Hub: remove the Roles view; split Skills and MCP Servers into project vs global scope

**Outcome (one sentence):** Config shows only actionable inventory: the static Roles view (repo YAML roster, a chain the banner already shows, outputs that are never recorded) is gone with its /api/roles routes, and Skills and MCP Servers each switch between the project's own entries and the machine-wide global ones.

## Read First
- docs/engineering/hub-architecture.md
- src/core/web/routes/roles.py
- src/core/web/routes/_config_read.py
- src/core/web/ui/src/features/config/SkillsTab.tsx

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the backend, **When** /openapi.json is read, **Then** no /api/roles path remains and the live-agent cards still show each agent's composed role chain.
- **Given** a machine with skills under each adapter's home skills_dir, **When** GET /api/config/skills is called, **Then** it returns them as global_skills with the adapters that load each, separate from the project skills.
- **Given** Config › Skills or Config › MCP Servers, **When** the operator flips the Project / Global switch, **Then** only that scope's entries are listed, each switch label carrying its count.

## Work Log
