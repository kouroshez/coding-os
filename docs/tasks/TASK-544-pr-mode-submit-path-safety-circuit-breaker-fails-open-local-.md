---
id: TASK-544
title: "pr-mode submit-path safety: circuit-breaker fails open + local-rung honesty + tmp race"
swimlane: core
kind: bug
epic: pr-mode-hardening
labels: [ready]
status: archive
priority: P1
appetite: 1d
created: 2026-06-24
started: 2026-06-24
completed: 2026-06-24
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-544: pr-mode submit-path safety: circuit-breaker fails open + local-rung honesty + tmp race

**Outcome (one sentence):** cos pr submit fails SAFE when gh is down (circuit breaker no longer counts unknown as 0 open PRs), the local autonomy rung emits an honest ahead/behind report with the exact manual-integration command, and ledger/heal-budget tmp writes use pid-unique names so concurrent writers cannot collide.

## Read First
- src/cli/pr_commands.py
- tests/test_cli.py
- src/core/hooks/_helpers/presence_write.py
- docs/playbooks/pr-workflow.md

## Repro Steps
In src/cli/pr_commands.py, _open_pr_count returns 0 when not _gh_ready() or gh pr list errors, so the per-session open-PR circuit breaker in pr_submit lets a push through in exactly the gh-down/quota-exhausted scenario it exists to stop. Separately the autonomy==local branch emits a generic not-pushed message, and _ledger_save/_heal_budget_save share a process-wide .json.tmp name that two concurrent writers collide on.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** gh is unavailable or `gh pr list` errors, **When** pr_submit runs the circuit breaker, **Then** the unknown count is treated as cap-reached and the push is refused (exit 1) rather than allowed.
- **Given** autonomy_level=local with N commits ahead of the integration branch, **When** pr submit runs, **Then** the output includes commits_ahead, behind, a stale flag when behind>0, and the exact `git diff <integration>..<branch>` review command; with 0 commits it says no commits to integrate yet.
- **Given** two concurrent _ledger_save / _heal_budget_save calls, **When** each writes its tmp file, **Then** the tmp names are pid-unique (path.name + .tmp.<pid>) so replace() never hits FileNotFoundError.
- **Given** the matrix verify, **When** `uv run pytest tests/test_cli.py -q` runs, **Then** it passes.

## Work Log
- 2026-06-24 [claude]: Edit git_settings_fields.py
- 2026-06-24 [claude]: Edit pr_commands.py
- 2026-06-24 [claude]: Edit pr_commands.py
- 2026-06-24 [claude]: Edit pr_commands.py
- 2026-06-24 [claude]: Edit cos-env.sh
- 2026-06-24 [claude]: Edit pr_commands.py
- 2026-06-24 [claude]: Edit cos-env.sh
- 2026-06-24 [claude]: Edit pr_commands.py
- 2026-06-24 [claude]: Edit pr_commands.py
- 2026-06-24 [claude]: Chose a -1 sentinel from _open_pr_count (over raising) so the breaker fails SAFE when gh is down — honoring the…
