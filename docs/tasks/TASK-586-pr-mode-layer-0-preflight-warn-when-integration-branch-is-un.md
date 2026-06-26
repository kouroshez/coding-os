---
id: TASK-586
title: "pr-mode Layer-0 preflight: warn when integration branch is unprotected on the remote + mark local-rung merge instruction human-only"
swimlane: core
kind: feature
epic: git-foundation-hardening
labels: [git, pr-mode, ux, preflight, ready]
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

# TASK-586: pr-mode Layer-0 preflight: warn when integration branch is unprotected on the remote + mark local-rung merge instruction human-only

**Outcome (one sentence):** Make the layered-defense model legible at the CLI: when pr-mode is on but the remote integration branch has NO server-side protection (no ruleset / required check), preflight and submit warn loudly that the client hook is the only wall (Layer-0 missing — the agent could be bypassed). And mark the `local` rung's printed `git merge --no-ff` instruction explicitly human-only, since branch-guard blocks the agent from running it on the shared checkout.

## Read First
- docs/playbooks/pr-workflow.md
- src/cli/pr_commands.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** pr-mode active with a remote present and the integration branch having no branch protection / no required status check, **When** `cos pr preflight` or `cos pr submit` runs, **Then** the emit includes an explicit `unprotected_integration` warning naming the missing server-side protection and pointing at the ruleset setup. **Given** autonomy_level=local, **When** `cos pr submit` prints the integrate instruction, **Then** the text states a HUMAN must run it in plain git outside the agent (the agent is branch-guard-blocked from `git merge` on the shared checkout). Verify: uv run pytest tests/test_cli.py::TestCosPr -q green.

## Work Log
