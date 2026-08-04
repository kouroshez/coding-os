---
id: TASK-884
title: "Modular-first messaging + CLI-only onboarding deep review + final IP sweep + docs alignment"
swimlane: core
kind: chore
epic: null
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-08-04
started: 2026-08-04
completed: 2026-08-04
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-884: Modular-first messaging + CLI-only onboarding deep review + final IP sweep + docs alignment

## Outcome
README/docs lead with the modular story (use only what you need — e.g. core+graph alone) and name the recommended profile during onboarding; the no-Hub `cos init` path is verified end-to-end (stacks/skills/modules handling) with gaps fixed; a final copyright/IP sweep confirms nothing embarrassing remains; GitHub docs and site stay consistent.

## Read First
- README.md, src/core/subsystems.yaml, src/cli/main.py (init flow)
- docs/architecture/meta-project.md § subsystem modules

## Acceptance
- GIVEN a user who only wants the graph WHEN they read the README THEN the modular story + exact command is visible above the fold.
- GIVEN a CLI-only user WHEN they follow docs without the Hub THEN init→stack→skills→verify works, executed proof.
- GIVEN the IP sweep WHEN it finishes THEN zero third-party copyrighted material remains in HEAD.

## Work Log
- 2026-08-04 [claude]: Edit README.md
- 2026-08-04 [claude]: Edit README.md
- 2026-08-04 [claude]: Edit meta-project.md
- 2026-08-04 [claude]: Edit workflow-guide.md
- 2026-08-04 [claude]: Edit config-composition.md
- 2026-08-04 [claude]: Edit README.md
- 2026-08-04 [claude]: Edit CONTRIBUTING.md
- 2026-08-04 [claude]: Edit pty_init.py
- 2026-08-04 [claude]: Edit raptor-consolidation.md
- 2026-08-04 [claude]: Edit pty_init.py
- 2026-08-04 [claude]: commit 414882d45d — chore(docs): final IP sweep — drop third-party slide asset, genericize names, credit Maven Wrapper
- 2026-08-04 [claude]: Edit main.py
- 2026-08-04 [claude]: Edit README.md
- 2026-08-04 [claude]: commit cf434fab4b — fix(cli): honest post-init next steps + document the Hub-optional CLI loop
- 2026-08-04 [claude]: All three reviews done + fixes shipped. Modularity: README hero + "Modular by design" section with verified…
- 2026-08-04 [claude]: Edit README.md
- 2026-08-04 [claude]: Edit release-please-config.json
- 2026-08-04 [claude]: commit 70a4699118 — fix(readme): dynamic GitHub release badge — works now the repo is public
- 2026-08-04 [claude]: Edit README.md
- 2026-08-04 [claude]: Edit workflow-guide.md
- 2026-08-04 [claude]: Edit workflow-guide.md
- 2026-08-04 [claude]: Edit NOTICE
- 2026-08-04 [claude]: Edit meta-project.md
- 2026-08-04 [claude]: Edit meta-project.md
- 2026-08-04 [claude]: Edit subsystems.yaml
- 2026-08-04 [claude]: Edit CONTRIBUTING.md
- 2026-08-04 [claude]: Edit screencast-guide.md
- 2026-08-04 [claude]: Edit README.md
- 2026-08-04 [claude]: Edit README.md
- 2026-08-04 [claude]: Edit README.md
- 2026-08-04 [claude]: Ten review agents landed after the fix pass; folded in what was still live — hub-extras missing from the core profile…
- 2026-08-04 [claude]: Status transitioned to complete via cos task-done.
- 2026-08-04 [claude]: committed 358ffe99 · 1 file
