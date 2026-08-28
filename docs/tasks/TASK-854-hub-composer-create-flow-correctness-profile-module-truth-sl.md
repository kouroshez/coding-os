---
id: TASK-854
title: "Hub Composer create-flow correctness \u2014 profile/module truth, slug payload, safe default folder"
swimlane: core
kind: bug
epic: null
labels: [hub, onboarding, composer, modules, ready]
status: archive
priority: P0
appetite: 1d
created: 2026-07-28
started: 2026-07-28
completed: 2026-07-28
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-854: Hub Composer create-flow correctness — profile/module truth, slug payload, safe default folder

**Outcome (one sentence):** A project created from the Hub Composer gets exactly the modules the UI showed, and the browser lands in the new project's chat.

## Read First
- docs/engineering/hub-architecture.md
- src/core/subsystems.yaml
- src/core/web/routes/hub.py
- src/core/web/ui/src/pages/OnboardingWizard.tsx

## Repro Steps
Open http://127.0.0.1:9188 → New project → Compose my own → python stack → Create.
1. `.coding-os/subsystems-state.json` of the new project disables `cognition` + `cicd` although every module chip was ON (init applies `default_profile: standard` and unions it with the wizard's list).
2. The browser stays on the project list instead of navigating to `/p/<slug>/workspace/chat` — `_parse_init_payload` scans for a single-line JSON object but `cos init --format json` prints `indent=2`, and the summary has no `slug` key at all.
3. The pre-filled parent folder is the coding-os checkout, so the dialog opens with a 400 "cannot scaffold inside the coding-os meta-repo checkout".
4. The `design` module is `hidden: true` in subsystems.yaml but still renders as a Composer chip.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the Composer with every module chip on, **When** the project is created, **Then** its `subsystems-state.json` disabled list is empty.
- **Given** a successful background create, **When** the job reports success, **Then** the result payload carries `slug` and the SPA navigates to that project's chat.
- **Given** the wizard opens while the hub runs inside the meta-repo, **When** the dialog renders, **Then** the pre-filled parent folder is a scaffoldable directory and no validation error is shown.
- **Given** subsystems.yaml marks a module hidden, **When** the Composer renders module chips, **Then** that module is absent.

## Work Log
- 2026-07-28 [claude]: Edit hub-architecture.md
- 2026-07-28 [claude]: Edit hub-architecture.md
- 2026-07-28 [claude]: Edit hub-architecture.md
- 2026-07-28 [claude]: Edit hub-architecture.md
- 2026-07-28 [claude]: Edit hub.py
- 2026-07-28 [claude]: Edit hub.py
- 2026-07-28 [claude]: Edit hub.py
- 2026-07-28 [claude]: Edit main.py
- 2026-07-28 [claude]: Edit main.py
- 2026-07-28 [claude]: Edit main.py
- 2026-07-28 [claude]: Edit main.py
- 2026-07-28 [claude]: Edit main.py
- 2026-07-28 [claude]: Edit cognition.py
- 2026-07-28 [claude]: Edit cognition.py
- 2026-07-28 [claude]: Edit hub.py
- 2026-07-28 [claude]: Edit HubHome.tsx
- 2026-07-28 [claude]: Edit HubHome.tsx
- 2026-07-28 [claude]: Edit OnboardingWizard.tsx
- 2026-07-28 [claude]: Edit OnboardingWizard.tsx
- 2026-07-28 [claude]: Edit OnboardingWizard.tsx
- 2026-07-28 [claude]: Edit OnboardingWizard.tsx
- 2026-07-28 [claude]: Edit OnboardingCard.tsx
- 2026-07-28 [claude]: Edit OnboardingCard.tsx
- 2026-07-28 [claude]: Edit OnboardingCard.tsx
- 2026-07-28 [claude]: Edit OnboardingCard.tsx
- 2026-07-28 [claude]: Edit HubHome.tsx
- 2026-07-28 [claude]: Edit HubHome.tsx
- 2026-07-28 [claude]: Edit HubHome.tsx
- 2026-07-28 [claude]: Edit HubHome.tsx
- 2026-07-28 [claude]: Edit HubHome.tsx
- 2026-07-28 [claude]: Edit HubHome.tsx
- 2026-07-28 [claude]: Edit HubHome.tsx
- 2026-07-28 [claude]: Edit HubHome.tsx
- 2026-07-28 [claude]: Edit OnboardingWizard.tsx
- 2026-07-28 [claude]: Edit OnboardingWizard.tsx
- 2026-07-28 [claude]: Edit OnboardingWizard.tsx
- 2026-07-28 [claude]: Edit new-project.md
- 2026-07-28 [claude]: Edit new-project.md
- 2026-07-28 [claude]: Edit hub-architecture.md
- 2026-07-28 [claude]: Edit hub-architecture.md
- 2026-07-28 [claude]: Edit hub-architecture.md
- 2026-07-28 [claude]: Edit meta-project.md
- 2026-07-28 [claude]: Edit README.md
- 2026-07-28 [claude]: Edit README.md
- 2026-07-28 [claude]: Edit README.md
- 2026-07-28 [claude]: Edit vision.md
- 2026-07-28 [claude]: Edit test_hub_init_route.py
- 2026-07-28 [claude]: Edit test_cli.py
- 2026-07-28 [claude]: Edit OnboardingWizard.test.tsx
- 2026-07-28 [claude]: Edit OnboardingWizard.test.tsx
- 2026-07-28 [claude]: Edit HubHome.tsx
- 2026-07-28 [claude]: committed 48b01215 · 13 files
- 2026-07-28 [claude]: Edit init_jobs.py
- 2026-07-28 [claude]: Edit init_jobs.py
- 2026-07-28 [claude]: Edit main.py
- 2026-07-28 [claude]: Edit main.py
- 2026-07-28 [claude]: Edit main.py
- 2026-07-28 [claude]: Edit ChatList.tsx
- 2026-07-28 [claude]: Edit first-run.spec.ts
- 2026-07-28 [claude]: commit 79a502612e — docs(onboarding): document the panel-first install path and the module/profile axis
- 2026-07-28 [claude]: Fixed + verified live in the browser: chips now seed from GET /modules::default_disabled and init is called with…
- 2026-07-28 [claude]: Status transitioned to complete via cos task-done.
