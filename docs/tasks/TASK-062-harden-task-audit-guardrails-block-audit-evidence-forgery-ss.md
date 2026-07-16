---
id: TASK-062
title: "Harden task/audit guardrails: block audit-evidence forgery (SS1) + nudge raw task lookups (SS2)"
swimlane: core
kind: bug
epic: workflow-integrity
labels: [hooks, guardrails, integrity, completion-guardian]
status: archive
priority: P1
appetite: "1d"
created: 2026-06-02
started: 2026-06-02
completed: 2026-06-02
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-062: Harden task/audit guardrails: block audit-evidence forgery (SS1) + nudge raw task lookups (SS2)

**Outcome (one sentence):** Close 3 guardrail holes from the tooling audit: (A1) enforce-task-transition.sh governance allow-list must still BLOCK audit EvidenceBundle/cos_supervise_record_output checkbox ticks; (A2) completion_guardian.py gains a runtime-independent check flagging an audit marked complete with no matching formula_dispatches row; (A3) nudge-task-discovery.sh gains a Read-leg WARN on docs/tasks/** + broadened Bash regex.

## Read First
- src/core/hooks/enforce-task-transition.sh
- src/core/hooks/_helpers/detect_status_transition.py
- src/core/hooks/nudge-task-discovery.sh
- src/core/thinking_os/completion_guardian.py
- docs/governance/critical-rules.md

## Repro Steps
1. With a governance/docs-update task marker active, hand-Edit a `audit-*.md` to mark the audit complete and tick its EvidenceBundle attestation line (the one naming cos_supervise_record_output).
2. Look a task up via raw `ls docs/tasks/ | grep -i NNN` + raw Read instead of `cos task-show`.
Expected: the audit-evidence tick is BLOCKED; a runtime-independent guardian flags the forged completion; a WARN nudges the raw lookup.
Actual: the governance allow-list lets the tick through; the guardian only cross-checks under intent.exhaustive; the nudge is Bash-only/once-per-session and never sees the raw Read.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a governance/docs-update marker is active, **When** an Edit ticks an audit `EvidenceBundle submitted`/`cos_supervise_record_output` checkbox, **Then** enforce-task-transition.sh BLOCKs it (exit 2) regardless of the allow-list.
- **Given** an audit-*.md shows `status: completed` (or `[x] EvidenceBundle submitted`) with NO matching formula_dispatches row, **When** completion_guardian runs at Stop, **Then** it emits a gap even when intent.exhaustive is unset, while still fail-opening on DB read errors.
- **Given** a raw `Read`/`ls|grep|cat` of docs/tasks/**, **When** no cos_task_show ran this session, **Then** nudge-task-discovery.sh WARNs (never blocks) on both the Bash and Read legs.
- **Given** the changes, **When** `make verify-hooks` + targeted guardian pytest run, **Then** all green.

## Work Log
- 2026-06-02 [claude]: A1: enforce-task-transition.sh exempts audit-*.md from the governance allow-list so a hand-ticked Evid
- 2026-06-02 [claude]: A1/A2/A3 committed 1701f1e + golden 62d0d92.. (per-stack). 50 tests green (43 guardian/workflow + 7 golden). Blocked-the
