---
id: TASK-555
title: "Config\u2192Git preset cards: highlight the ACTIVE preset, not the Recommended one (decouple selected-state from badge)"
swimlane: core
kind: bug
epic: pr-mode-hardening
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-06-24
started: 2026-06-24
completed: 2026-06-24
agent_session: ses-claude-20260624-154810-74c2
depends_on: []
blocked_by: []
references: []
---
# TASK-555: Config→Git preset cards: highlight the ACTIVE preset, not the Recommended one (decouple selected-state from badge)

**Outcome (one sentence):** In the Hub Config→Git quick-start presets, the "Recommended" badge and the visual "selected/active" state become independent. The accent-highlight reflects which preset matches the CURRENT form values (deep-equal incl. protected_branches set-equality), so the Recommended card no longer looks permanently selected and a clicked preset shows clear selected feedback. Improves config clarity for non-expert consumers.

## Read First
- src/core/web/ui/src/pages/ConfigPage.tsx
- docs/engineering/hub-architecture.md

## Repro Steps
Screenshot 1 (pr-mode OFF): the "Team + GitHub CI ★ Recommended" card renders with the accent border+background — looks selected though nothing is chosen. Screenshot 2: user clicked "main → dev → prod" but no card shows any selected indication. Root cause: ConfigPage.tsx:748 keys the selected-look class on preset.recommended instead of on whether the preset matches the current form.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** pr-mode is OFF / the form matches no preset, **When** the Git tab renders, **Then** no preset card shows the accent selected style (Recommended shows only its ★ badge).
- **Given** the user clicks "main → dev → prod", **When** the form updates, **Then** that card shows the active/selected accent style and the others do not.
- **Given** the form deep-equals a preset's apply values (incl. protected_branches as a set), **When** rendered, **Then** exactly that one card is active and its button carries aria-pressed=true.

## Work Log
- 2026-06-24 [claude]: Edit prmode_nojq.sh
- 2026-06-24 [claude]: Edit combined_test.sh
- 2026-06-24 [claude]: Edit ConfigPage.tsx
- 2026-06-24 [claude]: Edit ConfigPage.tsx
- 2026-06-24 [claude]: Edit ConfigPage.tsx
- 2026-06-24 [claude]: commit 170920414b — fix(hub): Config→Git highlights the active preset, not the Recommended badge
- 2026-06-24 [claude]: Decoupled preset "active/selected" from the recommended flag in ConfigPage.tsx GitTab: new isPresetActive(apply)…
