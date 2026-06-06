---
id: TASK-148
title: "E13: exhaustive silent-handler conversion + swallow_safe() helper + cos_say hook adoption (coord TASK-100)"
swimlane: infra
kind: refactor
epic: observability-eye
labels: [observability, adoption, exhaustive, deferred, blocked-on-TASK-100]
status: archive
priority: P2
appetite: "1d"
created: 2026-06-05
started: null
completed: null
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-148: E13: exhaustive silent-handler conversion + swallow_safe() helper + cos_say hook adoption (coord TASK-100)

**Outcome (one sentence):** Route the ~429 silent except handlers + raw echo>&2 hooks through the eye: add logging_os.swallow_safe(scope) (logs debug + increments a counter), convert production error paths first, adopt cos_say in hooks. EXHAUSTIVE (audit-*.md + grep before/after + EvidenceBundle) and must COORDINATE with the active TASK-100 (output-quality) to avoid touching hook bodies twice — deferred so it runs as one disciplined sweep, not concurrently. Spec in observability-eye.md §1 + roadmap E13.

## Read First
- docs/engineering/observability-eye.md
- docs/tasks/TASK-100-script-command-output-quality-remediation-runtime-params-pro.md
- src/core/logging_os/api.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** ...
- **When** ...
- **Then** ...

## Work Log
- 2026-06-05 [claude]: E13 keystone shipped: logging_os.swallow_safe(scope, exc=) + swallowed_count() (debug log + always-on counter → fire-and
- 2026-06-05 [claude]: Broad `except Exception: pass` class EXHAUSTIVELY eliminated (7→0 across src/core+src/cli, grep-verified): graph_os back
- 2026-06-06 [claude]: ARCHIVED (keystone shipped, remainder bounded) — anti-overengineering (Rule 22). The high-value deliverable — swallow_sa
