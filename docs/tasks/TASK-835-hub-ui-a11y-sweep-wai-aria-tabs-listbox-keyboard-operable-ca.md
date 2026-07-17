---
id: TASK-835
title: "Hub UI a11y sweep: WAI-ARIA tabs/listbox + keyboard-operable cards/rows/toggles (audit backlog)"
swimlane: core
kind: chore
epic: null
labels: [hub, frontend, a11y, audit, backlog, ready]
status: blocked
priority: P2
appetite: 1d
created: 2026-07-17
started: 2026-07-17
completed: null
agent_session: ses-claude-20260717-010539-6051
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
