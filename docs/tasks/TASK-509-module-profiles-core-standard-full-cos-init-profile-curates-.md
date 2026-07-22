---
id: TASK-509
title: "Module profiles (core/standard/full): cos init --profile curates the default tool surface"
swimlane: core
kind: feature
epic: null
labels: [ready]
status: archive
priority: P2
appetite: 1d
created: 2026-06-21
started: 2026-06-21
completed: 2026-06-21
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-509: Module profiles (core/standard/full): cos init --profile curates the default tool surface

**Outcome (one sentence):** cos init --profile <core|standard|full> (default standard) writes a curated subsystems-state.json so a fresh consumer's agent sees a leaner MCP tool surface (standard drops cognition's ~15 tools), reusing the existing module-disable machinery; a COMPLICATED+ classify with cognition off surfaces a discoverability nudge to enable it.

## Read First
- src/core/subsystems.yaml
- src/cli/subsystems.py
- src/cli/main.py
- src/cli/_init_helpers.py
- docs/engineering/modularity-audit-2026-06.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** cos init --profile standard (the default) **When** the project is scaffolded **Then** subsystems-state.json disables cognition (agent tool surface excludes the cognition family) AND --profile full disables nothing (byte-identical to today's all-on) AND --profile core additionally disables memory+observability AND an unknown profile name errors with the valid choices AND a COMPLICATED+ cos_classify_prompt with cognition disabled returns a hint naming `cos module enable cognition`.

## Work Log
- 2026-06-21 [claude]: Edit subsystems.yaml
- 2026-06-21 [claude]: Edit subsystems.py
- 2026-06-21 [claude]: Edit verify_profiles.py
- 2026-06-21 [claude]: Edit main.py
- 2026-06-21 [claude]: Edit main.py
- 2026-06-21 [claude]: Edit main.py
- 2026-06-21 [claude]: Edit capture_golden.py
- 2026-06-21 [claude]: Edit test_golden_parity.py
- 2026-06-21 [claude]: Edit cognition.py
- 2026-06-21 [claude]: Edit cognition.py
- 2026-06-21 [claude]: Edit test_cognition_tools.py
- 2026-06-21 [claude]: Edit test_module_gating_smoke.py
- 2026-06-21 [claude]: Edit modularity-audit-2026-06.md
- 2026-06-21 [claude]: commit 0fb4e75129 — feat(modularity): cos init --profile core/standard/full curates default tool surface (TASK-509)
- 2026-06-21 [claude]: Shipped the profile system: subsystems.yaml profiles (core/standard/full) + resolve_profile…
