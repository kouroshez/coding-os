---
id: TASK-462
title: "Architecture seam ADRs \u2014 symlink version-gate + cross-adapter orchestration"
swimlane: infra
kind: chore
epic: audit-remediation-2026-06
labels: [audit-remediation, governance, ready]
status: in_progress
priority: P2
appetite: 1d
created: 2026-06-20
started: 2026-06-19
completed: null
agent_session: ses-claude-20260619-211916-fd8f
depends_on: []
blocked_by: []
references: []
---
# TASK-462: Architecture seam ADRs — symlink version-gate + cross-adapter orchestration

**Outcome (one sentence):** Two "decide now, build when needed" seams from the strategic audit (group E) are captured as ADRs so the decision exists before the code does: (E1) the live-symlink core→consumer propagation has no version gate — decide the pre-first-consumer posture (ship a wheel/copy + a BLOCKing cos doctor version check vs editable symlinks); (E2) cross-adapter orchestration (the user's #1 differentiator) — record that the orchestrator belongs in core (the importlib per-agent dispatcher loader already supports multi-adapter, P8 is NOT the blocker), and the single decision is whether to relax the deliberate "one adapter per session" invariant (dispatcher.py:168-175). No implementation in this task — ADRs only.

## Work Log
- 2026-06-20 [claude]: Edit 0010-consumer-distribution-version-gate.md
- 2026-06-20 [claude]: Edit 0011-cross-adapter-orchestration-seam.md
