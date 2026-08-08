---
id: TASK-919
title: "Split cli/doctor.py into kernel + doctor_checks_* siblings"
swimlane: cli
kind: refactor
epic: null
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-08-08
started: 2026-08-08
completed: 2026-08-08
agent_session: ses-claude-20260807-224955-abc1
depends_on: []
blocked_by: []
references: []
---
# TASK-919: Split cli/doctor.py into kernel + doctor_checks_* siblings

**Outcome (one sentence):** doctor.py drops 2952 to ~576 lines keeping run_doctor/CLI/report types; six doctor_checks_* siblings hold the checks; cos doctor runs end-to-end green.

## Read First
- src/cli/doctor.py
- src/cli/doctor_graph.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the split **When** cos doctor and cos doctor --bootstrap run **Then** both exit 0 with all checks executed
- **Given** external importers (web settings route, generate_manifest) **When** they import names from cli.doctor **Then** imports resolve unchanged

## Work Log
- 2026-08-08 [claude]: Status transitioned to complete via cos task-done.
