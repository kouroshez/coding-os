---
id: TASK-1032
title: "Cross-provider review findings are persisted but never surfaced to the parent"
swimlane: infra
kind: bug
epic: null
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-08-31
started: null
completed: 2026-09-13
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-1032: Cross-provider review findings are persisted but never surfaced to the parent

**Outcome (one sentence):** A cross-provider review's verdict and findings reach the parent session in the same line that already reports its route and price, so a review that found problems can never read like a clean one.

## Read First
- src/core/hooks/_helpers/auto_dispatch.py (`_dispatch_one`)
- src/core/hooks/_helpers/dispatch_summary.py
- src/core/hooks/_session_pulse.sh (the read-once `.dispatch-results` consumer)

## Repro Steps
1. Move a task to `testing`; `auto-dispatch-crossprovider` fires `reviewer`
   and `security_auditor` on Codex, detached.
2. `_dispatch_one` appends role/adapter/model/status/cost/latency to
   `$COS_PANEL_DIR/.dispatch-results`. The role's own output — `passed`,
   `review_findings`, `findings` — goes only into the evidence bundle.
3. `dispatch_summary.py` renders `reviewer@codex/gpt-5.6-sol=ok$0.5612`.
Expected: the parent learns what the review found.
Actual: the parent learns a review happened and what it cost. A reviewer that
found three blocking problems renders identically to one that found none, so
the run buys false confidence on top of the tokens it already spent.

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** a dispatched review that returned findings
**When** the next session pulse renders
**Then** the line names how many findings there were and quotes the first of
them, inside the existing character budget.

**Given** a dispatched review that returned `passed: true` and no findings
**When** the line renders
**Then** it says so explicitly, rather than looking the same as a review whose
result was dropped.

**Given** a role whose output declares no verdict
**When** the line renders
**Then** it adds nothing, because an invented verdict is worse than none.

## Work Log
- 2026-09-14 [claude]: The pulse carried route and price only, so a reviewer that found three problems rendered identically to a clean one.…
- 2026-09-14 [claude]: Status transitioned to complete via cos task-done.
