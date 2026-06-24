---
id: TASK-556
title: "pr-mode driver STOP-on-green is not signal-derivable \u2014 green draft re-polls forever after /clear (D5)"
swimlane: cli
kind: bug
epic: pr-mode-hardening
labels: [ready]
status: complete
priority: P1
appetite: 1d
created: 2026-06-24
started: 2026-06-24
completed: 2026-06-24
agent_session: ses-claude-20260624-154810-74c2
depends_on: []
blocked_by: []
references: []
---
# TASK-556: pr-mode driver STOP-on-green is not signal-derivable — green draft re-polls forever after /clear (D5)

**Outcome (one sentence):** The driver's STOP-on-green-with-no-auto-merge decision becomes derivable from the single ci_rollup signal, not from cross-turn working memory — closing the green-draft infinite re-poll that undermines the "autonomous, never stops" guarantee across /clear, /compact, and reaper-handoff.

## Read First
- src/cli/pr_commands.py
- src/core/skills/pr-mode-driver/SKILL.md
- docs/playbooks/pr-workflow.md

## Repro Steps
_pr_ci_rollup (src/cli/pr_commands.py:666-676) queries only state,mergedAt,statusCheckRollup; a green draft-autonomy PR returns ci_rollup=passing, indistinguishable from a will-land armed PR. The SKILL's STOP (SKILL.md:37) leans on unpersisted agent working memory of the prior `cos pr submit` merge_status — lost on /clear, /compact, or a reaper-recovered fresh session → the driver re-polls a green draft PR every turn forever.

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** a green PR that will NOT auto-land (autonomy=draft, or degraded-no-required-check, or a GitHub draft PR), **When** `cos pr status --branch` runs, **Then** ci_rollup is `passing-unarmed` (not `passing`) so the driver STOPs from the signal alone.
**Given** a green PR with auto-merge armed (not a draft AND autoMergeRequest present), **When** status runs, **Then** ci_rollup is `passing` so the driver yields and waits for the land.
**Given** the pr-mode-driver SKILL, **When** read, **Then** the STOP branch keys on `passing-unarmed` with no dependency on a remembered prior `merge_status`, and the golden fixtures are recaptured.

## Work Log
- 2026-06-24 [claude]: Edit pr_commands.py
- 2026-06-24 [claude]: Edit pr_commands.py
- 2026-06-24 [claude]: Edit pr_commands.py
- 2026-06-24 [claude]: Edit pr_commands.py
- 2026-06-24 [claude]: Edit SKILL.md
- 2026-06-24 [claude]: Edit SKILL.md
- 2026-06-24 [claude]: Edit pr-workflow.md
- 2026-06-24 [claude]: Edit test_cli.py
- 2026-06-24 [claude]: Edit test_cli.py
- 2026-06-24 [claude]: commit ddb341ce37 — chore(golden): recapture stale block-shared-tree-edit goldens (TASK-554 realpath fallback)
- 2026-06-24 [claude]: commit e578778ca1 — fix(pr-mode): driver STOP-on-green is signal-derivable via passing-unarmed (D5)
- 2026-06-24 [claude]: Deliberation: chose to overload ci_rollup with a derived `passing-unarmed` value (one signal, the driver's "branch on…
