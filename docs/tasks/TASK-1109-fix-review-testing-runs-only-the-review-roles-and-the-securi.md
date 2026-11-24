---
id: TASK-1109
title: "fix(review): testing runs only the review roles, and the security auditor runs on sensitive diffs in both modes"
swimlane: "board_os"
kind: bug
epic: null
labels: [hooks, supervision, ready]
status: complete
priority: P1
appetite: 1d
created: 2026-11-24
started: 2026-11-24
completed: 2026-11-24
agent_session: ses-claude-20261124-100023-d989
depends_on: []
blocked_by: []
references: []
---
# TASK-1109: fix(review): testing runs only the review roles, and the security auditor runs on sensitive diffs in both modes

**Outcome (one sentence):** A move to testing dispatches the reviewer every round and the security auditor only when the task's own diff touches security-sensitive code, whether supervision is on or off. Supervision only picks the adapter and model of those two roles. The auditor re-runs on a later round only when the sensitive part of the diff changed or its last pass had a blocking finding.

## Read First
- docs/engineering/agent-supervision.md
- src/core/hooks/_helpers/auto_dispatch.py
- src/core/board_os/review_gate.py

## Repro Steps
With the live Hub policy and supervision on, review_targets(policy, "codex") returns 10 targets: analyst, architect (opus), debugger (opus), deployer, documenter, implementer, observer, refactorer, researcher on claude, plus reviewer@codex. One move to testing from a Codex session spawns nine non-review roles on the Claude subscription. Separately, security_auditor ran on every task when pinned (a docs-only card cost $1.35) and never ran when supervision was off.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** supervision is on and non-review roles are pinned to another adapter, **When** a task enters testing, **Then** only reviewer, plus security_auditor when due, are dispatched.
- **Given** reviewer or security_auditor is pinned to the session's own adapter, **When** they are dispatched, **Then** the pin's model and effort are used.
- **Given** a task whose linked commits touch no security-sensitive path, **When** it enters testing, **Then** only the reviewer runs, with supervision on or off.
- **Given** linked commits that touch a sensitive path (shell, hook helpers, auth/secret/token/permission/crypto names, CI workflows, Dockerfiles, dependency manifests, agent settings), **When** the task enters testing, **Then** the security auditor runs too, on its pin when supervision is on, else on the session's adapter.
- **Given** round 2 or later, **When** the sensitive diff is unchanged and the auditor's last pass had no blocking finding, **Then** the auditor is not re-run; otherwise it runs again.
- **Given** several review roles are due, **When** dispatch starts, **Then** every role's running row is written before the first review runs, so the gate never passes between two reviews.

## Work Log
- 2026-11-24 [claude]: Plan: replace cross_provider_roles with a review-only review_targets (reviewer always, security_auditor when due);…
- 2026-11-24 [claude]: commit 9f2e80c482 — fix(review): testing dispatches only review roles; security auditor runs on sensitive diffs
- 2026-11-24 [claude]: commit 6034ebf7a1 — fix(review): unquoted paths, wider sensitive list, and a review plan that cannot cost the round
- 2026-11-24 [claude]: Review round 2 (reviewer@claude + security_auditor@claude): passed, 0 blocking, 3 lows accepted. Imports outside the…
- 2026-11-24 [claude]: Status transitioned to complete via cos task-done.
