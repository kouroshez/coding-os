---
id: TASK-874
title: "Public-release readiness audit: cos update, PyPI, license, branch protection, docs, Codex parity, versioning, CI burn"
swimlane: core
kind: chore
epic: null
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-08-04
started: 2026-08-03
completed: 2026-08-03
agent_session: ses-claude-20260803-180632-5fca
depends_on: []
blocked_by: []
references: []
---
# TASK-874: Public-release readiness audit: cos update, PyPI, license, branch protection, docs, Codex parity, versioning, CI burn

## Outcome
A complete, evidence-backed readiness report for taking coding-os public on GitHub, answering: (1) how `cos update` reads/propagates to consumer projects, (2) PyPI publish path with uv, (3) license recommendation, (4) main-branch protection posture for contributors, (5) README/git-docs correctness + Codex adapter completeness, (6) first-release versioning path, (7) root cause of the 2,000-hour GitHub Actions quota burn with concrete remediation. Safe fixes applied where warranted.

## Read First
- docs/governance/release-process.md
- docs/engineering/adapter-parity.md
- .github/workflows/
- src/cli/ (update command)
- README.md

## Acceptance
- GIVEN the operator's 8 questions WHEN the report is delivered THEN each has a verified answer backed by repo/GitHub evidence, not memory.
- GIVEN the CI quota burn WHEN analyzed THEN the dominant cost driver is identified with measured run data and a remediation list.
- GIVEN release blockers WHEN found THEN each is listed with severity and the smallest corrective action.

## Work Log
- 2026-08-04 [claude]: Verified: repo PRIVATE (kouroshez/coding-os); LICENSE=Apache-2.0 + pyproject SPDX aligned; no branch protection…
- 2026-08-04 [claude]: Audit complete. CI burn: quota is 2000 MINUTES/mo (Gmail-verified), burned in 2 days by full-matrix-per-push (26…
- 2026-08-04 [claude]: Status transitioned to complete via cos task-done.
