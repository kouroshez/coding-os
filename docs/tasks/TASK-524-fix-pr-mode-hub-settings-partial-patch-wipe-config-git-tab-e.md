---
id: TASK-524
title: "Fix pr-mode hub settings partial-PATCH wipe + Config Git tab error/loading state"
swimlane: core
kind: bug
epic: multi-agent-pr-mode
labels: [pr-mode, pr-mode-hardening, hub, frontend, ready]
status: complete
priority: P2
appetite: 1d
created: 2026-06-22
started: 2026-06-22
completed: 2026-06-23
agent_session: ses-claude-20260622-134704-4de9
depends_on: []
blocked_by: []
references: []
---
# TASK-524: Fix pr-mode hub settings partial-PATCH wipe + Config Git tab error/loading state

> **Re-materialized 2026-06-24 (TASK-532).** Reconstructed from the board DB metadata + the shipping commit `6ba34da5`. The original body was never persisted (the task closed without a file ever written → `body` is null in the DB and the file never existed in git), so Outcome / Read First / Acceptance below are faithfully reconstructed from the title and the committed diff; the Work Log records the real commit.

**Outcome (one sentence):** A partial `git_settings` PATCH no longer wipes sibling fields — the settings route merges per-section with `exclude_unset` — and the Config → Git tab surfaces explicit loading / error / unavailable states for the git-state fetch instead of an empty panel.

## Read First
- src/core/web/routes/settings.py
- src/core/web/ui/src/pages/ConfigPage.tsx

## Repro Steps
PATCH `/api/settings` with only `git_settings.enabled` → the other `git_settings` keys (`integration_branch`, `protected_branches`) were dropped (full-object replace). And the Config → Git tab rendered blank while git-state was loading or when the endpoint failed, with no signal to the operator.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a partial `git_settings` PATCH **When** `/api/settings` applies it **Then** unset sibling fields are preserved (per-section merge, `exclude_unset`).
- **Given** the Config → Git tab **When** git-state is loading or the fetch fails **Then** an explicit loading / error / unavailable state renders (no silent empty panel).
- **And** `uv run pytest tests/test_hub_settings_git.py -q` is green.

## Work Log
- 2026-06-23 [claude]: Shipped in commit 6ba34da5 — merge partial settings PATCH (exclude_unset) + surface git-state loading/error/unavailable in the Config Git tab.
- 2026-06-24 [claude]: File re-materialized from DB metadata (TASK-532); original body unrecoverable (never persisted to disk / git).
