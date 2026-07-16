---
id: TASK-166
title: "Review fixes (TASK-165 reviewer) — commit codemod, delete dead BrainGraph3D, theme-store test + sync"
swimlane: core
kind: chore
epic: ui-design-system
labels: [ui, design-system, review-fix, ready]
status: archive
priority: P1
appetite: "1d"
created: 2026-06-05
started: 2026-06-05
completed: 2026-06-05
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-166: Review fixes (TASK-165 reviewer) — commit codemod, delete dead BrainGraph3D, theme-store test + sync

**Outcome (one sentence):** Close the non-overengineering reviewer findings: F1 — version-control the color codemod + contrast/ΔE verification scripts into src/core/web/ui/scripts/ so 'repeatable' is real; F2 — delete the dead/unmounted BrainGraph3D.tsx (zero references, stale palette, last hardcoded color); F4 — unify theme on the theme-store as single source (board tweaks select + header toggle both write the store; providers subscribe so tweaks.theme never goes stale); F3 — add a vitest unit test for theme-store (toggle/persist/data-theme). make ui-build green + vitest passes.

## Work Log
- 2026-06-05 [claude]: Shipped (commits e7e2636 + 963ddeb): F4 — theme unified on the zustand theme-store as single source: DesignThemeProvider
