---
id: TASK-533
title: "Hub Git: replace absent push-toggle with an autonomy_level (Draft / Auto-merge / Autonomous) per the Trust Spectrum"
swimlane: core
kind: feature
epic: pr-mode-hardening
labels: [pr-mode, hub, autonomy-level, ready]
status: icebox
priority: P3
appetite: 1d
created: 2026-06-23
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-533: Hub Git: replace absent push-toggle with an autonomy_level (Draft / Auto-merge / Autonomous) per the Trust Spectrum

**Outcome (one sentence):** git_settings gains an autonomy_level enum (draft = agent opens PR, human merges; auto_merge = agent arms gh pr merge --auto on green; autonomous = full lifecycle incl. cleanup) that subsumes the user's 'does the agent push/merge itself' ask in the industry-standard Trust Spectrum framing (DeployHQ); cos pr submit honors it (draft never arms auto-merge), one Hub Config→Git control sets it with exclude_unset persistence, and the default is the safe 'draft'.

## Read First
- src/core/web/routes/settings.py
- src/core/web/ui/src/pages/ConfigPage.tsx
- src/cli/pr_commands.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** autonomy_level=draft **When** cos pr submit runs **Then** it opens the PR and does NOT arm auto-merge.
- **Given** autonomy_level=auto_merge and a green required check **When** submit runs **Then** auto-merge is armed.
- **Given** the Hub Git tab **When** the level is changed and PATCHed **Then** it persists per-section (exclude_unset) and cos-env exports it without wiping siblings.
- **And** `uv run pytest tests/test_cli.py -q` + the settings route tests are green.

## Work Log
