---
id: TASK-881
title: "Donate page: replace GitHub embed iframes with native sponsor CTA (dark-mode polish)"
swimlane: docs
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
# TASK-881: Donate page: replace GitHub embed iframes with native sponsor CTA (dark-mode polish)

## Outcome

coding-os.dev/donate drops both GitHub Sponsors iframes (they break the dark theme and look off-brand) in favor of a native, design-system CTA (glass featured card + primary button), deployed and screenshot-verified in dark mode.

## Read First

- cos-website: src/frontend/app/donate/page.tsx (current iframes)
- cos-website: app/community/page.tsx (buttonVariants + cn CTA pattern to mirror)

## Acceptance

- Given https://coding-os.dev/donate in dark mode, when loaded logged-out, then no GitHub iframe renders and a native featured GitHub Sponsors card with a primary "Sponsor on GitHub" button matches the site design system.
- Given the change, when running typecheck and lint, then both pass.

## Work Log
- 2026-08-04 [claude]: Edit page.tsx
- 2026-08-04 [claude]: Edit page.tsx
- 2026-08-04 [claude]: Edit page.tsx
- 2026-08-04 [claude]: Edit page.tsx
- 2026-08-04 [claude]: Edit page.tsx
- 2026-08-04 [claude]: Dropped both GitHub Sponsors iframes; native glass featured card + primary Sponsor button (cos-website 383feed).…
- 2026-08-04 [claude]: Status transitioned to complete via cos task-done.
