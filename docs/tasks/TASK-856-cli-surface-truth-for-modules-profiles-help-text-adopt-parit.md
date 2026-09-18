---
id: TASK-856
title: "CLI surface truth for modules/profiles \u2014 help text, adopt parity, onboarding-status honesty"
swimlane: core
kind: bug
epic: null
labels: [cli, modules, profiles, docs-drift, ready]
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
- 2026-07-28 [claude]: Help text for --disable-module/--profile is now derived from subsystems.yaml (Rule 11) so lite is discoverable and…
- 2026-07-28 [claude]: Status transitioned to complete via cos task-done.
- 2026-07-28 [claude]: commit 2dee5b63ae — chore(board): sync drifted task files and regenerated indexes
- 2026-07-28 [claude]: commit 123747eadd — chore(board): commit closing task-file state for the onboarding fix batch
- 2026-07-28 [claude]: commit 5f0a2d4c33 — chore(board): record commit trail on the closed onboarding tasks
- 2026-07-28 [claude]: Edit main.py
- 2026-07-28 [claude]: Edit main.py
- 2026-07-28 [claude]: Edit hub.py
- 2026-07-28 [claude]: Edit hub.py
- 2026-07-28 [claude]: Edit cognition.py
- 2026-07-28 [claude]: Edit cognition.py
- 2026-07-28 [claude]: Edit main.py
- 2026-07-28 [claude]: Edit AppShell.tsx
- 2026-07-28 [claude]: Edit index.css
- 2026-07-28 [claude]: Edit HubPrimitives.test.tsx
- 2026-07-28 [claude]: commit b7df636905 — fix(hub): close module sets over dependents and let the onboarding marker expire
- 2026-07-28 [claude]: Edit probe_state.py
- 2026-07-29 [claude]: Edit setup.py
- 2026-07-29 [claude]: Edit setup.py
- 2026-07-29 [claude]: Edit main.py
- 2026-07-29 [claude]: Edit cognition.py
- 2026-07-29 [claude]: Edit cognition.py
- 2026-07-29 [claude]: Edit main.py
- 2026-07-29 [claude]: Edit test_cli.py
- 2026-07-29 [claude]: Edit subsystems.py
- 2026-07-29 [claude]: Edit main.py
- 2026-07-29 [claude]: Edit hub.py
- 2026-07-29 [claude]: Edit hub.py
- 2026-07-29 [claude]: Edit OnboardingWizard.tsx
- 2026-07-29 [claude]: Edit OnboardingCard.tsx
- 2026-07-29 [claude]: Edit hub-architecture.md
- 2026-07-29 [claude]: Edit hub-architecture.md
- 2026-07-29 [claude]: Edit main.py
- 2026-07-29 [claude]: Edit test_hub_init_route.py
- 2026-07-29 [claude]: Edit stub-api.ts
- 2026-07-29 [claude]: commit b729f9241c — fix(onboarding): keep readiness on one signal and stop json mode emitting prose
