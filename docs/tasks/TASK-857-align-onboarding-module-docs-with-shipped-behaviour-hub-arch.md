---
id: TASK-857
title: "Align onboarding + module docs with shipped behaviour (hub-architecture, meta-project, README, vision)"
swimlane: docs
kind: chore
epic: null
labels: [docs-update, onboarding, modules, ready]
status: archive
priority: P1
appetite: 1d
created: 2026-07-28
started: 2026-07-28
completed: 2026-07-28
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-857: Align onboarding + module docs with shipped behaviour (hub-architecture, meta-project, README, vision)

**Outcome (one sentence):** The docs a new adopter reads describe the install paths, module profiles, and first-run screens that actually ship.

## Read First
- docs/engineering/hub-architecture.md
- docs/architecture/meta-project.md
- README.md
- docs/governance/vision.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** `subsystems.yaml` ships four profiles, **When** a reader opens the architecture and hub docs, **Then** all four (including `lite`) and the module-vs-profile interaction are documented in one SSOT section.
- **Given** ADR-0007's GUI-first install path, **When** a reader opens README, **Then** the one-command install and the panel-first create flow are the front-door path.
- **Given** the hub home empty state and Composer, **When** a reader opens hub-architecture.md, **Then** the first-run screen contract is specified rather than implied.

## Work Log
- 2026-07-28 [claude]: Docs aligned: hub-architecture gained the first-run screen contract, the modules-endpoint contract (hidden excluded +…
- 2026-07-28 [claude]: Status transitioned to complete via cos task-done.
