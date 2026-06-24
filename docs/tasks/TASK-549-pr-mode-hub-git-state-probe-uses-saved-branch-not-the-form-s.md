---
id: TASK-549
title: "pr-mode Hub git-state probe uses saved branch, not the form-selected one (capability pills lie)"
swimlane: core
kind: bug
epic: pr-mode-hardening
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-06-24
started: 2026-06-24
completed: 2026-06-24
agent_session: ses-claude-20260624-034200-e9e7
depends_on: []
blocked_by: []
references: []
---
# TASK-549: pr-mode Hub git-state probe uses saved branch, not the form-selected one (capability pills lie)

**Outcome (one sentence):** GET /api/settings/git-state accepts an optional `integration` query param and probes that branch; the Hub Config→Git tab passes the form-selected integration_branch and keys the React-Query cache by it, so the required_check / pr_ok pills and the auto_merge gating warning reflect the branch the user is editing, not the last-saved one.

## Read First
- src/core/web/routes/settings.py
- src/cli/pr_commands.py
- src/core/web/ui/src/pages/ConfigPage.tsx
- src/core/web/ui/src/lib/hooks.ts
- tests/test_hub_settings_git.py

## Repro Steps
In Config→Git with pr-mode on, change the Integration branch dropdown to a branch with a different required-check status than the saved one; the "required CI" pill and the "no required status check" auto_merge warning do not update — they keep showing the saved branch's status because the route hardcodes `_preflight(repo, _integration_branch(repo))` (settings.py ~L150) and the UI query key omits the branch (ConfigPage.tsx ~L465).

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** pr-mode is enabled and a user selects a different integration branch in the Config→Git dropdown, **When** the git-state probe runs, **Then** `_preflight` is called with the form-selected branch (verified via a route test asserting `?integration=<x>` reaches `_preflight`) and the required-CI pill + auto-merge warning reflect that branch, not the saved one.

## Work Log
- 2026-06-24 [claude]: Edit settings.py
- 2026-06-24 [claude]: Edit ConfigPage.tsx
- 2026-06-24 [claude]: Edit test_hub_settings_git.py
- 2026-06-24 [claude]: Route get_git_state(integration: str | None) probes integration or _integration_branch(repo); ConfigPage GitTab…
- 2026-06-24 [claude]: committed 31a82ff5 · 3 files
