---
id: TASK-553
title: "Git tab hidden behind read-only wall on meta-repo \u2014 render full configurator on every project"
swimlane: core
kind: bug
epic: pr-mode-hardening
labels: [ready]
status: complete
priority: P1
appetite: 1d
created: 2026-06-24
started: 2026-06-24
completed: 2026-06-24
agent_session: ses-claude-20260624-034200-e9e7
depends_on: []
blocked_by: []
references: []
---
# TASK-553: Git tab hidden behind read-only wall on meta-repo — render full configurator on every project

**Outcome (one sentence):** The Config→Git tab renders the full editable configurator (quick-start presets, per-field InfoTips, integration/protected branch controls, autonomy dropdown) on EVERY project including coding-os. The meta-repo read-only dead-box (GitTabReadOnly + the slug==='coding-os' gate) and the misleading static top-right "read-only" page badge are both removed. coding-os's trunk-default is preserved by enabled=false (the saved default), not by hiding the UI; a single slim caution line on the meta-repo notes that enabling pr-mode there switches the mother repo off trunk.

## Read First
- src/core/web/ui/src/pages/ConfigPage.tsx
- src/core/web/ui/src/pages/ConfigPage.test.tsx
- docs/architecture/adr/0013-pr-mode-multi-agent-git-workflow-consumer-only.md

## Repro Steps
Open the Hub on the coding-os project → Config → Git. The tab shows only a "coding-os itself stays trunk" read-only box plus a static "read-only" badge top-right; none of the TASK-552 configurator (InfoTips, presets, branch controls) is reachable. The developer cannot see or interact with the feature on the default/dogfood project.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the active project is coding-os, **When** the user opens Config→Git, **Then** the full editable tab renders (presets, per-field InfoTips, branch controls, autonomy) — not a read-only dead box.
- **Given** any project, **When** the Config page header renders, **Then** the static top-right "read-only" badge is gone (it falsely labeled editable tabs as read-only).
- **Given** coding-os with pr-mode never enabled, **When** the tab loads, **Then** enabled defaults false (meta-repo stays trunk) and a single slim caution line notes enabling switches the mother repo off trunk.
- **Given** the GitTab vitest suite, **When** it runs, **Then** the meta-repo test asserts the full tab (preset + InfoTip present) instead of the removed banner, and tsc + vite build stay green.

## Work Log
- 2026-06-24 [claude]: Edit ConfigPage.tsx
- 2026-06-24 [claude]: Edit ConfigPage.tsx
- 2026-06-24 [claude]: Edit ConfigPage.tsx
- 2026-06-24 [claude]: Edit ConfigPage.tsx
- 2026-06-24 [claude]: Edit ConfigPage.tsx
- 2026-06-24 [claude]: Edit ConfigPage.tsx
- 2026-06-24 [claude]: Edit ConfigPage.test.tsx
- 2026-06-24 [claude]: commit ebb25fd25a — fix(hub): render full Config→Git tab on every project; drop meta-repo read-only wall
- 2026-06-24 [claude]: Removed the meta-repo read-only wall: GitTab now renders the full editable configurator on every project (slug-gate →…
