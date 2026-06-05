---
id: TASK-164
title: "Cortex dark-mode contrast fix — board card tokens, badges, priority + global theme toggle"
swimlane: core
kind: bug
epic: ui-design-system
labels: [ui, dark-mode, contrast, a11y, board, ready]
status: complete
priority: P0
appetite: "1d"
created: 2026-06-05
started: 2026-06-05
completed: 2026-06-05
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-164: Cortex dark-mode contrast fix — board card tokens, badges, priority + global theme toggle

**Outcome (one sentence):** Fix the broken dark mode surfaced by the board screenshot: every TaskCard color was hardcoded for the legacy light pastel sticky note (title #141210 → invisible on dark, id #3a3530, meta #4a4540, label #6b665e, priority outline #c0392b/#ea580c garish, chip bg rgba(0,0,0,.06) wrong on dark, kind badge #fff-on-solid fails on amber/lime). Replace ALL with themed --cos-* tokens (title→cos-text, id/meta→cos-muted, label→cos-faint), convert the kind badge to a tinted pill (chip-color text on a faint color-mix tint) and priorityStyle to a single themed thin outline (P0 cos-err, P1 cos-warn, P2/P3 none) so cards are calm not garish. Verify every text/background pair with a programmatic WCAG contrast check (≥4.5 normal / ≥3 large) in BOTH themes. Add a global dark/light toggle to the AppShell header via a zustand theme-store (persisted, applies data-theme) and init DesignThemeProvider from it. Sweep other pages for hardcoded dark text. make ui-build green.

## Read First
- src/core/web/ui/src/features/cos-board/CosBoardPage.tsx
- src/core/web/ui/src/layout/AppShell.tsx
- src/core/web/ui/src/design/ThemeProvider.tsx
- docs/engineering/design-system.md

## Repro Steps
1. Open the Hub at http://127.0.0.1:9188 in dark mode (the default) and go to the Board.
2. Observe any task card title + badges.
Expected: card title and metadata clearly legible; calm, professional colors.
Actual: title near-invisible (hardcoded `#141210` on a dark card), priority draws a garish red/orange full outline, kind badge `#fff`-on-solid can fail — every card color was authored for the old light pastel sticky note.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the Board renders in dark mode (the default) — and again in light mode
- **When** task cards, badges, priority markers and the global header render
- **Then** every card text/background pair meets WCAG AA (≥4.5 body / ≥3 large) verified by a programmatic contrast check in BOTH themes (0 failures), no hardcoded sticky-era hex remains on cards, the kind badge is a legible tinted pill, priority is a single calm themed outline (P0/P1 only), and a persisted dark/light toggle sits in the global AppShell header; make ui-build green

Spec SSOT: [docs/engineering/design-system.md](../engineering/design-system.md)

## Work Log
- 2026-06-05 [claude]: Shipped (commit 64e4647): root cause = every TaskCard color hardcoded for the old light pastel sticky (title #141210 inv
