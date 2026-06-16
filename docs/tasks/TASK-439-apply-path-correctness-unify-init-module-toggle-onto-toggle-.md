---
id: TASK-439
title: "Apply-path correctness: unify init module-toggle onto toggle_and_regen (fix SI-1), module-aware doctor consistency check, guard cos module against the meta-repo"
swimlane: infra
kind: bug
epic: null
labels: [modularity, apply-path, doctor, dogfood, audit-2026-06, ready]
status: complete
priority: P1
appetite: 1d
created: 2026-06-16
started: 2026-06-16
completed: 2026-06-16
agent_session: ses-803-0b9f
depends_on: [TASK-438]
blocked_by: []
references: []
---
# TASK-439: Apply-path correctness: unify init module-toggle onto toggle_and_regen (fix SI-1), module-aware doctor consistency check, guard cos module against the meta-repo

**Outcome (one sentence):** init and runtime share ONE module-toggle apply-path, so a module disabled at init is fully disabled (tools AND hooks), doctor can prove the disabled-hook-scripts allowlist matches subsystems-state.json, and running cos module inside the meta-repo never clobbers the hand-written AGENTS.md. Closes audit R2+R3+R4 (problem-tree Branch A + Branch D).

## Read First
- src/cli/module_commands.py
- src/cli/main.py
- src/cli/project_overrides.py
- src/cli/subsystems.py
- src/cli/doctor.py

## Repro Steps
cos init --disable-module graph in a temp project → .coding-os/disabled-hook-scripts is absent/empty while subsystems-state.json lists graph disabled → graph hooks still fire. Separately: render_agents_md output (~12.8k generic) differs from the hand-written meta AGENTS.md (~10.8k), so a meta-repo toggle overwrites it.

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** `cos init --disable-module graph` **When** init completes **Then** .coding-os/disabled-hook-scripts lists the graph hooks (they self-skip) — init routes through the same write_runtime_allowlist path as `cos module disable`, not a direct set_module_enabled.

**Given** a project whose disabled-hook-scripts is inconsistent with subsystems-state.json **When** `cos doctor` runs **Then** it reports the drift; and a disabled-graph project is no longer nagged to run graph-reindex (doctor is module-aware).

**Given** `cos module disable <id>` invoked inside the coding-os meta-repo (CLAUDE.md symlinked to a hand-written AGENTS.md) **When** the toggle runs **Then** the MCP/hook gates still apply via state but the hand-written AGENTS.md is NOT rewritten (self-dogfood detected and skipped, or the toggle refuses with a clear message).

**Given** these changes **When** `uv run pytest tests/test_cli.py -q` runs **Then** new regression tests for SI-1, the doctor check, and the meta-repo guard pass.

## Work Log
- 2026-06-16 [claude]: Edit main.py
- 2026-06-16 [claude]: Edit module_commands.py
- 2026-06-16 [claude]: Edit doctor.py
- 2026-06-16 [claude]: Edit doctor.py
- 2026-06-16 [claude]: Edit doctor.py
- 2026-06-16 [claude]: Edit test_cli.py
- 2026-06-16 [ses-803-0b9f]: SI-1: init now calls write_runtime_allowlist after module-toggle loop (main.py) → disabled-hook-scripts written at init,
