---
id: TASK-480
title: "Module-disable skill-surface completeness: init unlinks owned skill, AGENTS.md ## Skills gated, idempotent relink over dangling symlink"
swimlane: cli
kind: bug
epic: null
labels: [modularity, audit-pass5, skills, ready]
status: archive
priority: P1
appetite: 1d
created: 2026-06-20
started: 2026-06-20
completed: 2026-06-20
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-480: Module-disable skill-surface completeness: init unlinks owned skill, AGENTS.md ## Skills gated, idempotent relink over dangling symlink

**Outcome (one sentence):** A module disabled at init OR runtime fully sheds its owned skills from BOTH the on-disk adapter skills dir AND the rendered AGENTS.md `## Skills` list, and re-enable/relink is idempotent over a dangling symlink. Closes adversarially-verified audit findings D2-1 (HIGH), D2-2 (HIGH), D1-2 (LOW bug), D6-5 (LOW test). Init and runtime module-disable reach skill-parity (TASK-439 unified tools+hooks but NOT skills).</outcome>

## Read First
- docs/engineering/modularity-audit-2026-06.md
- src/cli/_init_helpers.py
- src/cli/skill_commands.py
- src/cli/aggregator.py

## Repro Steps
In a temp dir run the init path with a module disabled (e.g. graph): the graph-owned skills (graph-explorer, graph-os-authoring) remain symlinked in the adapter skills dir AND still appear in the rendered AGENTS.md `## Skills` list, whereas `cos module disable graph` correctly unlinks them — proving the init/runtime skill-cascade divergence. Separately, a dangling skill symlink makes Path.exists() False so the relink helper takes the symlink_to() branch and raises FileExistsError.

## Acceptance (G/W/T) — *this IS the Definition of Done*

- **Given** a consumer scaffolded with a module disabled at init, **When** init completes, **Then** that module's owned core skills are NOT symlinked into the adapter skills dir (parity with runtime `cos module disable`).
- **Given** a module disabled (init or runtime), **When** AGENTS.md is rendered, **Then** the disabled module's owned skills do NOT appear in the `## Skills` (INSTALLED_SKILLS) list.
- **Given** a dangling skill symlink, **When** `cos skill enable <name>` or module re-enable runs, **Then** relink is idempotent (no FileExistsError) and points to the real SKILL.md.
- **Given** the module-gating smoke test, **When** it asserts module_state_payload, **Then** it also asserts the per-module skills count.
- **Given** the all-modules-on default, **When** the consumer AGENTS.md + skills dir are rendered, **Then** golden parity is unchanged (byte-identical render).

## Work Log
- 2026-06-20 [claude]: Edit skill_commands.py
- 2026-06-20 [claude]: Edit skill_commands.py
- 2026-06-20 [claude]: Edit renderer.py
- 2026-06-20 [claude]: Edit renderer.py
- 2026-06-20 [claude]: Edit main.py
- 2026-06-20 [claude]: Edit _verify_d22.py
- 2026-06-20 [claude]: Edit _verify_d22.py
- 2026-06-20 [claude]: Edit test_cli.py
- 2026-06-20 [claude]: Edit test_modularity_toggle.py
- 2026-06-20 [claude]: Edit test_modularity_toggle.py
- 2026-06-20 [claude]: Edit test_module_gating_smoke.py
- 2026-06-20 [claude]: Implemented D2-1 (init step 5c runs ref-counted cascade_module_skills for disabled modules), D2-2 (renderer…
- 2026-06-20 [claude]: committed 6b761096 · 6 files
