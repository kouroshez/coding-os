---
id: TASK-481
title: "Bind the commands axis to the module registry \u2014 disabled module sheds its slash commands (data-driven commands: + cascade + doctor drift)"
swimlane: cli
kind: feature
epic: null
labels: [modularity, audit-pass5, commands, ready]
status: complete
priority: P2
appetite: 1d
created: 2026-06-20
started: 2026-06-20
completed: 2026-06-20
agent_session: ses-claude-20260620-150945-6eba
depends_on: [TASK-480]
blocked_by: []
references: []
---
# TASK-481: Bind the commands axis to the module registry — disabled module sheds its slash commands (data-driven commands: + cascade + doctor drift)

**Outcome (one sentence):** subsystems.yaml gains a per-module `commands:` field; enabling/disabling a module links/unlinks its owned slash-commands in the consumer commands dir at BOTH init and runtime (mirroring the skills cascade); `cos doctor` gains a warn-only `modules.command_drift` check; a disabled module is truly "as if it never existed" across the command surface. Closes audit D1-1 (the one cascade axis the owner explicitly requires but pass-4 deferred). Completes the registry's "owns everything a module owns" contract (parity with the F9 hooks-must-have-owner invariant).</outcome>

## Read First
- docs/engineering/modularity-audit-2026-06.md
- src/core/subsystems.yaml
- src/cli/module_commands.py
- src/cli/update.py
- src/cli/doctor.py

## Acceptance (G/W/T) — *this IS the Definition of Done*

- **Given** `cos module disable tasks`, **When** the cascade runs, **Then** /board /daily /retro /task are unlinked from the consumer commands dir.
- **Given** a disabled `tasks` module, **When** `cos module enable tasks` runs, **Then** those commands are relinked.
- **Given** a module disabled at init, **When** the scaffold is produced, **Then** its commands are absent from the consumer commands dir (init/runtime parity).
- **Given** a disabled module whose command file is still present, **When** `cos doctor` runs, **Then** `modules.command_drift` WARNs (not blocks).
- **Given** the all-modules-on default, **When** the consumer is rendered, **Then** the installed command set is byte-identical to before (no regression); commands owned by no module (kernel-level) are always linked.

## Work Log
- 2026-06-20 [claude]: Edit subsystems.yaml
- 2026-06-20 [claude]: Edit subsystems.yaml
- 2026-06-20 [claude]: Edit subsystems.yaml
- 2026-06-20 [claude]: Edit subsystems.yaml
- 2026-06-20 [claude]: Edit subsystems.py
- 2026-06-20 [claude]: Edit subsystems.py
- 2026-06-20 [claude]: Edit module_commands.py
- 2026-06-20 [claude]: Edit module_commands.py
- 2026-06-20 [claude]: Edit main.py
- 2026-06-20 [claude]: Edit doctor.py
- 2026-06-20 [claude]: Edit doctor.py
- 2026-06-20 [claude]: Edit test_modularity_toggle.py
- 2026-06-20 [claude]: Edit test_cli.py
- 2026-06-20 [claude]: Implemented commands cascade axis: subsystems.yaml commands: on…
- 2026-06-20 [claude]: committed 660f3167 · 7 files
