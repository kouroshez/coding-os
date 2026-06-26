---
id: TASK-588
title: "Add `auto` git mode: preflight-driven trunk-vs-pr selection (protected remote \u2192 pr, local \u2192 trunk)"
swimlane: core
kind: feature
epic: git-foundation-hardening
labels: [git, pr-mode, auto-mode, ready]
status: icebox
priority: P2
appetite: 1d
created: 2026-06-26
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-588: Add `auto` git mode: preflight-driven trunk-vs-pr selection (protected remote → pr, local → trunk)

**Outcome (one sentence):** Remove the manual per-project trunk-vs-pr choice while keeping the safe trunk floor: a consumer sets git mode to `auto`, and the system resolves the effective mode from the existing `_preflight` capability probe — pr (worktree→PR) when a usable remote+gh exist, trunk (direct commit) when local-only. Reuses _preflight; adds no new probing subsystem. This is the 'do the right thing' default the layered-defense analysis identified as the one real product gap.

## Read First
- src/cli/pr_commands.py
- src/core/hooks/cos-env.sh
- src/core/web/routes/settings.py
- src/core/web/ui/src/pages/ConfigPage.tsx
- docs/playbooks/pr-workflow.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** git mode=auto and remote+gh+required-check present, **When** the agent works a task, **Then** it isolates in a worktree and publishes via PR (pr behavior). **Given** mode=auto and a local-only repo (no remote), **When** the agent works, **Then** it behaves as trunk (direct commit to the integration branch). **Given** mode=auto surfaced in Hub Config→Git, **When** the tab loads, **Then** the UI shows the resolved effective mode (trunk|pr) from the live preflight, not just the literal 'auto'. **Given** git mode unset (default), **When** any hook resolves COS_GIT_WORKFLOW, **Then** behavior stays byte-identical to trunk. Verify: uv run pytest tests/test_cli.py -q AND settings + ConfigPage tests green.

## Work Log
