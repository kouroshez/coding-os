---
id: TASK-998
title: "governance: fix the eight defects the adversarial review confirmed before pushing"
swimlane: infra
kind: bug
epic: null
labels: [ready]
status: icebox
priority: P1
appetite: 1d
created: 2026-08-17
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-998: governance: fix the eight defects the adversarial review confirmed before pushing

**Outcome (one sentence):** Nothing in the unpushed range publishes a false remediation, a false credential green, or a stack rule that silently stays stale in a second adapter.

## Read First
- src/scripts/ablation_probe.py

## Repro Steps
1. (fill in: exact steps to reproduce)
2. ...
Expected: ...
Actual: ...

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** ANTHROPIC_MODEL exported and no real key, **When** preflight runs, **Then** the credential check still fails.
- **Given** two adapters holding the same untouched rule, **When** cos update refreshes, **Then** every adapter's copy moves and no file is both refreshed and kept.
- **Given** a stale or absent mirror, **When** cos update runs, **Then** it reports the baseline is missing rather than asserting the user edited the file.

## Work Log
- 2026-08-17 [claude]: Edit ablation_probe.py
- 2026-08-17 [claude]: Edit ablation_probe.py
- 2026-08-17 [claude]: Edit ablation_probe.py
- 2026-08-17 [claude]: Edit ablation_probe.py
- 2026-08-17 [claude]: Edit ablation_probe.py
- 2026-08-17 [claude]: Edit ablation_probe.py
- 2026-08-17 [claude]: Edit ablation_probe.py
- 2026-08-17 [claude]: Edit ablation_probe.py
- 2026-08-17 [claude]: Edit ablation_probe.py
- 2026-08-17 [claude]: Edit ablation_probe.py
- 2026-08-17 [claude]: Edit ablation_probe.py
- 2026-08-17 [claude]: Edit _init_scaffold.py
- 2026-08-17 [claude]: Edit _init_scaffold.py
- 2026-08-17 [claude]: Edit _init_scaffold.py
- 2026-08-17 [claude]: Edit update.py
- 2026-08-17 [claude]: Edit update.py
- 2026-08-17 [claude]: Edit update.py
- 2026-08-17 [claude]: Edit test_stack_rule_refresh.py
- 2026-08-17 [claude]: Edit ablation-protocol.md
- 2026-08-17 [claude]: Edit ablation-protocol.md
- 2026-08-17 [claude]: Edit AGENTS.md
- 2026-08-17 [claude]: commit cf62f5d26c — fix(eval): stop the preflight greening on config vars and VM total
