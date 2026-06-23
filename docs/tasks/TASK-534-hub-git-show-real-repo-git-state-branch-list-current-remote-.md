---
id: TASK-534
title: "Hub Git: show real repo git-state (branch list / current / remote) + branch dropdowns instead of blind free-text"
swimlane: core
kind: feature
epic: pr-mode-hardening
labels: [pr-mode, hub, git-state, api-contract, ready]
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

# TASK-534: Hub Git: show real repo git-state (branch list / current / remote) + branch dropdowns instead of blind free-text

**Outcome (one sentence):** The Config→Git tab loads and shows the project's ACTUAL git state (branch list, current branch, remote URL) — not just a pr-mode capability probe — and renders integration_branch as a dropdown + protected_branches as a multiselect sourced from that list, so a consumer cannot silently set a non-existent branch; the gh-api capability probe is cached (TanStack staleTime) and short-circuited when git_settings.enabled is false.

## Read First
- src/core/web/routes/settings.py
- src/core/web/ui/src/pages/ConfigPage.tsx

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the Git tab opens **When** git-state loads **Then** it returns + renders the branch list, current branch and remote URL (not only capability pills).
- **Given** the branch list **When** the user picks integration_branch / protected_branches **Then** they choose from a dropdown/multiselect, not free text, and a non-existent value warns at save.
- **Given** git_settings.enabled=false **When** the tab opens **Then** the gh-api probe is skipped/cached (no per-open round-trip).
- **And** the settings route tests + UI build are green.

## Work Log
