---
id: TASK-592
title: "pr-mode auto-merge deadlock on CODEOWNERS / required-reviews: _has_required_check probes only status-checks, not review requirements"
swimlane: core
kind: bug
epic: git-foundation-hardening
labels: [pr-mode, auto-merge, codeowners, critic-found, ready]
status: archive
priority: P2
appetite: 1d
created: 2026-06-26
started: 2026-06-26
completed: 2026-06-26
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-592: pr-mode auto-merge deadlock on CODEOWNERS / required-reviews: _has_required_check probes only status-checks, not review requirements

**Outcome (one sentence):** Critic-found critical breakpoint (real-world OSS / regulated use cases). `_has_required_check` (pr_commands.py:211-225) probes ONLY `branches/<b>/protection/required_status_checks`; it never checks `required_pull_request_reviews` / CODEOWNERS. So on a repo whose ruleset requires N approvals (the standard enterprise + OSS-fork + finance config), `cos pr submit` at auto_merge/autonomous sees required_check=true, arms `gh pr merge --auto --squash`, and the PR sits green-but-unmergeable forever (no human approves, the agent moved on) — a silent deadlock the existing no-required-check escalation does NOT catch. Fix: extend the capability probe to detect a review requirement and add a `reviewDecision==REVIEW_REQUIRED` branch to _rollup_state so the pr-mode-driver STOPs for a human approval (like passing-unarmed) instead of waiting on auto-merge that will never fire.

## Read First
- src/cli/pr_commands.py
- docs/playbooks/pr-workflow.md
- docs/architecture/adr/0013-pr-mode-multi-agent-git-workflow-consumer-only.md

## Repro Steps
Configure a GitHub ruleset on main: require a PR + require 1 approving review + a required status check. Set autonomy_level=auto_merge. Run cos pr open/submit; CI goes green. The PR never merges (no approval) and the agent receives no deadlock signal — _has_required_check returned true so the no-required-check escalation never fires.

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** an integration branch whose ruleset requires >=1 approving review, **When** `cos pr submit` runs at autonomy=auto_merge with a green required check, **Then** it does NOT silently rely on auto-merge — it surfaces that a human approval is required (and/or does not arm, escalating like the no-required-check path). **Given** `cos pr status --branch`, **When** the PR is green but blocked on review, **Then** ci_rollup returns a distinct review-required signal (not `passing`/`passing-unarmed`). **Given** no review requirement, **When** submit runs, **Then** behavior is unchanged. Verify: uv run pytest tests/test_cli.py::TestCosPr -q green + new tests.

## Work Log
- 2026-06-26 [claude]: Plan: deviate from the task's suggested protection-API probe — use the PR's own `reviewDecision` (read via `gh pr…
- 2026-06-26 [claude]: Edit pr_commands.py
- 2026-06-26 [claude]: Edit pr_commands.py
- 2026-06-26 [claude]: Edit pr_commands.py
- 2026-06-26 [claude]: Edit pr_commands.py
- 2026-06-26 [claude]: Edit pr_commands.py
- 2026-06-26 [claude]: Edit pr_commands.py
- 2026-06-26 [claude]: Edit pr_commands.py
- 2026-06-26 [claude]: Edit test_cli.py
- 2026-06-26 [claude]: Edit test_cli.py
- 2026-06-26 [claude]: Edit pr-workflow.md
- 2026-06-26 [claude]: Edit pr-workflow.md
- 2026-06-26 [claude]: Edit multi-agent-git-use-cases.md
- 2026-06-26 [claude]: committed c32a5f74 · 4 files
