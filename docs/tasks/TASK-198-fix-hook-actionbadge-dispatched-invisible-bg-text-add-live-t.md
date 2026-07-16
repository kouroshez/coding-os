---
id: TASK-198
title: "Fix hook ActionBadge \u2014 dispatched invisible (bg=text), add live-tint, kill label truncation, verify all status contrast"
swimlane: core
kind: bug
epic: ui-design-system
labels: [ui, dashboard, contrast, a11y, ready]
status: archive
priority: P1
appetite: 1d
created: 2026-06-06
started: 2026-06-05
completed: 2026-06-05
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-198: Fix hook ActionBadge — dispatched invisible (bg=text), add live-tint, kill label truncation, verify all status contrast

**Outcome (one sentence):** Fix the Mission Control RECENT HOOKS status badges (DashboardPage ActionBadge): the codemod mapped cyan→--cos-live with no tint, so 'dispatched' got bg=text=--cos-live (a solid block with invisible text); add a --cos-live-tint token (both themes) and use bg=live-tint/text=live. Give neutral statuses (skip/non-rename/session-end/skip-not-replace) a visible bg (was --cos-panel = invisible on the panel). Kill the slice(0,9) truncation that clipped 'DISPATCHE'/'NON-RENAM' — render a short per-action label, auto-width, no clip. Programmatically verify EVERY badge fg/bg pair (info/err/warn/ok/brand/live/neutral) meets AA in BOTH light and dark. make ui-build green.

## Read First
- src/core/web/ui/src/pages/DashboardPage.tsx
- src/core/web/ui/public/cos-board-tokens.css
- docs/engineering/design-system.md

## Repro Steps
1. Open Mission Control (Dashboard) and look at the RECENT HOOKS panel.
2. Find a `dispatched` hook event (e.g. auto-prune-deleted-files) — and a `skip`/`non-rename` one.
Expected: every status badge has readable text on a distinct, themed background.
Actual: `dispatched` is a solid block with INVISIBLE text (bg=text=--cos-live, the codemod mapped cyan→live with no tint); `skip`/`non-rename`/`session-end` have bg=--cos-panel = invisible pill on the panel; labels are clipped by slice(0,9) → "DISPATCHE", "NON-RENAM".

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the RECENT HOOKS panel in light mode and again in dark mode
- **When** any hook status badge (info/err/warn/ok/brand/live/neutral) renders
- **Then** every badge text is legible on its own themed background (≥3:1, programmatically verified both themes = 0 failures), `dispatched` uses --cos-live-tint bg / --cos-live text (no more bg=text), neutral statuses have a visible bg, no label is clipped (short per-action labels, auto-width), and `make ui-build` is green

## Work Log
- 2026-06-06 [claude]: Shipped (commit 261acf9): root cause = the color codemod mapped cyan/teal → --cos-live but live had no -tint token, so A
