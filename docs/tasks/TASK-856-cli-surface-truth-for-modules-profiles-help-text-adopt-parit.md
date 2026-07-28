---
id: TASK-856
title: "CLI surface truth for modules/profiles \u2014 help text, adopt parity, onboarding-status honesty"
swimlane: core
kind: bug
epic: null
labels: [cli, modules, profiles, docs-drift, ready]
status: icebox
priority: P1
appetite: 1d
created: 2026-07-28
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-856: CLI surface truth for modules/profiles — help text, adopt parity, onboarding-status honesty

**Outcome (one sentence):** Every module/profile choice the kernel supports is discoverable and identical from `cos init`, `cos adopt`, and the agent recipe.

## Read First
- src/core/subsystems.yaml
- src/cli/main.py
- src/core/commands/new-project.md

## Repro Steps
1. `cos init --help` omits the `lite` profile and lists a wrong module set for `--disable-module` (`design` is hidden; `cognition`/`observability`/`cicd` are missing).
2. `cos adopt --help` accepts neither `--profile` nor `--disable-module`, so a brownfield repo silently gets `standard` with no way to choose.
3. `src/core/commands/new-project.md` never mentions `--profile` and repeats the stale module list, so an agent-driven create can never reach `lite`/`full`.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the module registry, **When** `cos init --help` renders, **Then** the profile and module lists are derived from `subsystems.yaml` and exclude hidden modules.
- **Given** a brownfield repo, **When** `cos adopt --profile lite` runs, **Then** the adopted project's `subsystems-state.json` matches the `lite` profile.
- **Given** the agent recipe, **When** an agent reads `new-project.md`, **Then** `--profile` and the accurate module list are documented.

## Work Log
