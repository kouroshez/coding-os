---
id: TASK-540
title: "pr-mode `local` autonomy rung (no-push) + Config\u2192Git auto-discovery (disable invalid rungs + degraded badges)"
swimlane: core
kind: feature
epic: multi-agent-pr-mode
labels: [ready]
status: complete
priority: P1
appetite: 1d
created: 2026-06-24
started: 2026-06-24
completed: 2026-06-24
agent_session: ses-claude-20260623-225054-17eb
depends_on: []
blocked_by: []
references: []
---
# TASK-540: pr-mode `local` autonomy rung (no-push) + Config→Git auto-discovery (disable invalid rungs + degraded badges)

**Outcome (one sentence):** A consumer chooses per-project in Hub Config→Git whether the agent pushes at all. The `local` rung (lowest Trust-Spectrum step, below draft) makes `cos pr submit` commit in the worktree but NEVER push/PR — works with no remote at all (beginner/solo/air-gapped); a human integrates the branch. The panel auto-discovers repo capability (remote/gh/required-check) and disables or warns the rungs the repo cannot support, data-driven. Closes the user's "agent stays local or pushes remote?" ask without a CLI-only gap. CI-gate principle preserved (pr-workflow.md §8 line 121): autonomy never bypasses CI — `local` is about whether the agent pushes, not whether CI gates.

## Read First
- docs/playbooks/pr-workflow.md
- src/cli/pr_commands.py
- src/core/web/ui/src/pages/ConfigPage.tsx
- src/core/web/routes/settings.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** autonomy_level=local, **When** `cos pr submit` runs in a repo with no remote, **Then** it exits 0 with merge_status=local and pushed=False, opens no PR, calls no gh, and the agents/* branch stays local.
**Given** the Config→Git probe reports no remote or no gh, **When** the autonomy dropdown renders, **Then** only `local` is selectable and the push/PR rungs are visibly disabled with a reason.
**Given** autonomy_level=auto_merge and the integration branch has no required check, **When** the tab renders, **Then** an amber degraded warning is shown (auto-merge will not arm).

## Work Log
- 2026-06-24 [claude]: Edit pr-workflow.md
- 2026-06-24 [claude]: Edit pr-workflow.md
- 2026-06-24 [claude]: Edit pr-workflow.md
- 2026-06-24 [claude]: Edit settings.py
- 2026-06-24 [claude]: Edit settings.py
- 2026-06-24 [claude]: Edit pr_commands.py
- 2026-06-24 [claude]: Edit pr_commands.py
- 2026-06-24 [claude]: Edit ConfigPage.tsx
- 2026-06-24 [claude]: Edit ConfigPage.tsx
- 2026-06-24 [claude]: Edit test_cli.py
- 2026-06-24 [claude]: Edit test_hub_settings_git.py
- 2026-06-24 [claude]: Shipped `local` rung: submit short-circuits before the capability probe (no remote needed), commit-only,…
- 2026-06-24 [claude]: committed 53dcb48d · 6 files
