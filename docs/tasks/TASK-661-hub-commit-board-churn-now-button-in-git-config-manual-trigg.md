---
id: TASK-661
title: "Hub: \"Commit board churn now\" button in Git config \u2014 manual trigger for the board-drift sweep"
swimlane: core
kind: feature
epic: null
labels: [hub, board-coherence, ux, ready]
status: archive
priority: P3
appetite: 1d
created: 2026-06-30
started: null
completed: null
agent_session: ses-claude-20260628-125542-fc9a
depends_on: []
blocked_by: []
references: []
---
# TASK-661: Hub: "Commit board churn now" button in Git config — manual trigger for the board-drift sweep

**Outcome (one sentence):** A "Commit board churn now" button in the Hub Git config tab (under Autonomy) lets the user trigger the board-drift sweep on demand instead of waiting for the 03:00 cron — staging + committing only docs/tasks/*.md in one tasks-only commit (autonomy-independent: the click IS the consent) and showing the resulting sha + file count, or "tree clean / no drift".

## Read First
- src/core/scheduled/nightly.py
- src/core/web/routes/settings.py
- src/core/web/ui/src/pages/ConfigPage.tsx
- src/core/board_os/git_coherence.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** uncommitted board drift (docs/tasks/*.md) **When** the user clicks "Commit board churn now" in the Hub Git tab **Then** a POST route stages + commits ONLY docs/tasks/*.md in one chore(board): commit and the UI shows the short sha + count. **Given** a clean tree **When** clicked **Then** the UI shows "nothing to commit" without erroring. **Then** the new route has a test, the UI typechecks + ConfigPage tests pass, and the bundle is rebuilt.

## Work Log
