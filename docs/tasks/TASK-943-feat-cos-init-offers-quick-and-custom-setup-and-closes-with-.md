---
id: TASK-943
title: "feat: cos init offers quick and custom setup and closes with a completion panel"
swimlane: cli
kind: feature
epic: null
labels: [ready]
status: icebox
priority: P1
appetite: 1d
created: 2026-08-12
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-943: feat: cos init offers quick and custom setup and closes with a completion panel

**Outcome (one sentence):** An interactive cos init lets the user choose between recommended defaults and answering every question, prints the defaults it applied, and ends with a panel naming where the files went and the commands to run next including how to upgrade.

## Read First
- src/cli/init_command.py
- src/cli/_init_phase.py
- src/cli/_init_prompts.py
- src/templates/_presets

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** an interactive terminal **When** cos init runs with no flags **Then** the user is offered a quick path that applies recommended defaults and prints them, and a custom path that also asks preset, profile and modules. **Given** either path completes **When** the scaffold finishes **Then** a completion panel lists the config, state and docs locations plus the next commands including the upgrade command. **Given** --yes or a non-TTY **When** cos init runs **Then** behaviour is unchanged and nothing is prompted.

## Work Log
