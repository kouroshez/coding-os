---
id: TASK-835
title: "Hub UI a11y sweep: WAI-ARIA tabs/listbox + keyboard-operable cards/rows/toggles (audit backlog)"
swimlane: core
kind: chore
epic: null
labels: [hub, frontend, a11y, audit, backlog, ready]
status: complete
priority: P2
appetite: 1d
created: 2026-07-17
started: 2026-07-17
completed: 2026-07-23
agent_session: ses-claude-20260723-213518-14b3
depends_on: []
blocked_by: []
references: []
---
# TASK-835: Hub UI a11y sweep: WAI-ARIA tabs/listbox + keyboard-operable cards/rows/toggles (audit backlog)

**Outcome (one sentence):** Complete the WAI-ARIA patterns flagged by the audit: proper tablist/tab/tabpanel with roving arrow-keys (ConfigPage, ObservabilityPage), keyboard-operable + focusable task cards (CosBoard) and table rows (Sessions), Toggle switch as a real button with Space/Enter (SettingsPage), listbox/aria-expanded semantics (SearchPage), consistent modal focus-traps, and programmatic labels on free-text inputs.

## Work Log
- 2026-07-17 [claude]: Edit SettingsPage.tsx
- 2026-07-17 [claude]: Edit CosBoardPage.tsx
- 2026-07-17 [claude]: Edit view-mode-tabs.tsx
- 2026-07-17 [claude]: Edit view-mode-tabs.tsx
- 2026-07-17 [claude]: Edit commit-835.txt
- 2026-07-17 [claude]: commit 8dfe962da3 — fix(hub): keyboard-operable switch toggles + WAI-ARIA tablist nav (TASK-835)
- 2026-07-17 [claude]: DONE this pass (committed 8dfe962d, verified: tsc clean + 197 vitest + 3 new tablist tests): (a) SettingsPage Toggle…
- 2026-07-24 [claude]: Resumed: plan = implement remaining a11y items (ConfigPage/Observability tablist roles+roving arrows,…
- 2026-07-24 [claude]: Edit use-roving-tablist.ts
- 2026-07-24 [claude]: Edit view-mode-tabs.tsx
- 2026-07-24 [claude]: Edit view-mode-tabs.tsx
- 2026-07-24 [claude]: Edit view-mode-tabs.tsx
- 2026-07-24 [claude]: Edit ConfigPage.tsx
- 2026-07-24 [claude]: Edit ConfigPage.tsx
- 2026-07-24 [claude]: Edit ObservabilityPage.tsx
- 2026-07-24 [claude]: Edit ObservabilityPage.tsx
- 2026-07-24 [claude]: Edit ObservabilityPage.tsx
- 2026-07-24 [claude]: Edit commit-835b.txt
- 2026-07-24 [claude]: commit 6212163329 — fix(hub): a11y sweep — WAI-ARIA tablists/listbox + keyboard-operable rows/cards (TASK-835)
- 2026-07-24 [claude]: COMPLETE (committed 62121633; verified tsc clean + 205 vitest pass + eslint 0-err + vite build OK): remaining…
- 2026-07-24 [claude]: Status transitioned to complete via cos task-done.
