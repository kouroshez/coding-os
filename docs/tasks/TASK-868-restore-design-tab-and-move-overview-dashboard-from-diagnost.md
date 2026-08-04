---
id: TASK-868
title: "Restore Design tab and move Overview dashboard from Diagnostics into Workspace"
swimlane: core
kind: chore
epic: null
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-08-03
started: 2026-08-03
completed: 2026-08-03
agent_session: ses-claude-20260803-153956-0acf
depends_on: []
blocked_by: []
references: []
---
# TASK-868: Restore Design tab and move Overview dashboard from Diagnostics into Workspace

**Outcome (one sentence):** The Design coming-soon tab is restored to Workspace (operator decision reversing TASK-864's removal) and the Overview dashboard moves from Diagnostics into Workspace as its first tab, with redirects preserving old URLs.

## Acceptance (G/W/T)

- Given /p/<slug>/workspace, when opened, then tabs are Overview · Chat · Board · Search · Memory · Design with chat still the default landing.
- Given /p/<slug>/diagnostics, when opened, then it lands on Doctor and no Overview tab remains; /diagnostics/overview and legacy /dashboard redirect to workspace overview.
- Given the restored Design tab, when clicked, then the coming-soon surface renders as before TASK-864.

## Work Log
- 2026-08-03 [claude]: Edit App.tsx
- 2026-08-03 [claude]: Edit App.tsx
- 2026-08-03 [claude]: Edit App.tsx
- 2026-08-03 [claude]: Edit App.tsx
- 2026-08-03 [claude]: Edit App.tsx
- 2026-08-03 [claude]: Edit WorkspacePage.tsx
- 2026-08-03 [claude]: Edit WorkspacePage.tsx
- 2026-08-03 [claude]: Edit DiagnosticsPage.tsx
- 2026-08-03 [claude]: Edit DiagnosticsPage.tsx
- 2026-08-03 [claude]: Edit hub-architecture.md
- 2026-08-03 [claude]: Edit hub-architecture.md
- 2026-08-03 [claude]: Edit hub-architecture.md
- 2026-08-03 [claude]: commit d7f041431b — feat(hub): move Overview into Workspace and restore the Design tab
- 2026-08-03 [claude]: Restored DesignComingSoon page+test from git history (0c6e6656^); Workspace tabs now…
- 2026-08-03 [claude]: Status transitioned to complete via cos task-done.
- 2026-08-04 [claude]: committed 12dd1ca9 · 1 file
