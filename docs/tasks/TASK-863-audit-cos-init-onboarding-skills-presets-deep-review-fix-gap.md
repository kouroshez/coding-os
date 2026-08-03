---
id: TASK-863
title: "Audit cos init onboarding: skills + presets deep review, fix gaps and preset-selection UX"
swimlane: cli
kind: spike
epic: null
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-08-03
started: 2026-08-03
completed: 2026-08-03
agent_session: ses-claude-20260803-125831-52f5
depends_on: []
blocked_by: []
references: []
---
# TASK-863: Audit cos init onboarding: skills + presets deep review, fix gaps and preset-selection UX

## Outcome

The `cos init` onboarding flow's skills and presets are fully inventoried, deep-reviewed, and repaired: every listed skill/preset resolves to real content, popular stacks are represented in the preset layer, and the manual-preset selection step is either clarified or removed from the interactive flow.

## Read First

- src/cli/ (init command + preset handling)
- src/core/thinking_os/presets/registry.yaml
- src/core/skills/ + src/templates/*/skills/
- docs/playbooks/template-authoring.md
- docs/architecture/meta-project.md

## Acceptance

- Given the full skill/preset inventory, when each entry is resolved, then no dangling references or empty/broken skill dirs remain.
- Given the preset registry, when a user onboards with a popular stack (nextjs, django, fastapi, laravel, ...), then a matching preset (or documented rationale for absence) exists.
- Given the interactive `cos init` flow, when the preset question is reached, then the choice presented is unambiguous (no manual-preset confusion) or the step is auto-derived.

## Work Log
- 2026-08-03 [claude]: Edit audit_onboarding.py
- 2026-08-03 [claude]: Edit mern.yaml
- 2026-08-03 [claude]: Edit nuxt-fullstack.yaml
- 2026-08-03 [claude]: Edit laravel-vue.yaml
- 2026-08-03 [claude]: Edit go-react.yaml
- 2026-08-03 [claude]: Edit hub.py
- 2026-08-03 [claude]: Edit OnboardingWizard.tsx
- 2026-08-03 [claude]: Edit OnboardingWizard.tsx
- 2026-08-03 [claude]: Edit OnboardingWizard.tsx
- 2026-08-03 [claude]: Edit OnboardingWizard.test.tsx
- 2026-08-03 [claude]: Edit OnboardingWizard.test.tsx
- 2026-08-03 [claude]: Edit test_hub_init_route.py
- 2026-08-03 [claude]: Edit main.py
- 2026-08-03 [claude]: Edit config-composition.md
- 2026-08-03 [claude]: Deliberation: scripted referential audit (skills/stacks/presets) before any fix — honors minimal-context +…
- 2026-08-03 [claude]: Audit results: 45 core + 27 template skills all schema-valid (0 dangling refs, 0 thin bodies, 72/72…
- 2026-08-03 [claude]: commit 4fb5ad5dd2 — feat(hub): tag presets with provenance and clarify the composer preset choice
- 2026-08-03 [claude]: commit 54c69dff76 — feat(cli): mention --preset in the interactive stack prompt
- 2026-08-03 [claude]: Status transitioned to complete via cos task-done.
