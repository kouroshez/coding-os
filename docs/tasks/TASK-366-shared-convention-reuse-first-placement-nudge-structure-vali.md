---
id: TASK-366
title: "shared/ convention + reuse-first placement nudge + structure validation (doctor --structure)"
swimlane: core
kind: feature
epic: J-anatomy
labels: [wave-5, onboarding-program, ready]
status: complete
priority: P1
appetite: 2d
created: 2026-06-11
started: 2026-06-13
completed: 2026-06-13
agent_session: ses-claude-20260613-120154-405b
depends_on: [TASK-351, TASK-355]
blocked_by: []
references: []
---
# TASK-366: shared/ convention + reuse-first placement nudge + structure validation (doctor --structure)

**Outcome (one sentence):** shared/{contracts,&lt;lang&gt;}/ convention is documented and encoded in clean-code + stack skills; a reuse-first nudge hook suggests promoting reused code to shared/; enforce-scaffold-boundary extended for the anatomy; `cos doctor --structure` validates tree vs declared anatomy; consumer AGENTS.md renders a data-driven anatomy map.

## Read First
- src/core/hooks/enforce-scaffold-boundary.sh
- src/core/skills/clean-code/SKILL.md
- src/cli/doctor.py
- src/core/hooks/registry.yaml

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the anatomy doc + skills, **When** a consumer project scaffolds, **Then** its AGENTS.md shows the project's actual anatomy map (data-driven from installed stacks) including shared/contracts as the cross-language boundary.
- **Given** the nudge hook registered in registry.yaml (sources cos-env.sh, $COS_* vars only, debounced), **When** an edit duplicates a symbol already used across services (heuristic), **Then** a single non-blocking stderr nudge suggests shared/&lt;lang&gt;/ placement — `make verify-hooks` green.
- **Given** a tree violating the declared anatomy (stray top-level src dir, service outside services/), **When** `cos doctor --structure` runs, **Then** each violation is listed with the expected location; a compliant tree returns 0.
- **Given** the matrix, **When** `make verify-hooks` + `uv run pytest tests/test_cli.py -q` run, **Then** green.

## Work Log
- 2026-06-13 [claude]: Edit SKILL.md
- 2026-06-13 [claude]: Edit SKILL.md
- 2026-06-13 [claude]: Edit SKILL.md
- 2026-06-13 [claude]: Edit SKILL.md
- 2026-06-13 [claude]: Edit _data_types.py
- 2026-06-13 [claude]: Edit _data_types.py
- 2026-06-13 [claude]: Edit aggregator.py
- 2026-06-13 [claude]: Edit aggregator.py
- 2026-06-13 [claude]: Edit aggregator.py
- 2026-06-13 [claude]: Edit renderer.py
- 2026-06-13 [claude]: Edit base.yaml
- 2026-06-13 [claude]: Edit anatomy-map.md.tmpl
- 2026-06-13 [claude]: Edit doctor.py
- 2026-06-13 [claude]: Edit doctor.py
- 2026-06-13 [claude]: Edit doctor.py
- 2026-06-13 [claude]: Edit _nudge_reuse_first.py
- 2026-06-13 [claude]: Edit nudge-reuse-first.sh
- 2026-06-13 [claude]: Edit registry.yaml
- 2026-06-13 [claude]: Edit test_aggregator.py
- 2026-06-13 [claude]: Edit test_renderer.py
- 2026-06-13 [claude]: Edit test_renderer.py
- 2026-06-13 [claude]: Edit test_doctor_structure.py
- 2026-06-13 [claude]: Edit test_nudge_reuse_first.py
- 2026-06-13 [claude]: Edit doctor.py
- 2026-06-13 [claude]: Edit test_doctor_structure.py
- 2026-06-13 [claude]: commit 559bc25bfa — feat(anatomy): data-driven AGENTS.md anatomy map + doctor --structure + reuse-first nudge
- 2026-06-13 [claude]: commit cadd131cc6 — chore(golden): propagate reuse-first hook into consumer fixtures
- 2026-06-13 [claude]: Edit doctor.py
- 2026-06-13 [claude]: Edit _nudge_reuse_first.py
- 2026-06-13 [claude]: Edit _nudge_reuse_first.py
- 2026-06-13 [claude]: Edit test_doctor_structure.py
- 2026-06-13 [claude]: Edit test_doctor_structure.py
- 2026-06-13 [claude]: Edit test_nudge_reuse_first.py
- 2026-06-13 [claude]: Edit test_nudge_reuse_first.py
- 2026-06-13 [claude]: Edit test_nudge_reuse_first.py
- 2026-06-13 [claude]: Edit test_aggregator.py
- 2026-06-13 [claude]: Edit test_shared_convention_docs.py
- 2026-06-13 [claude]: commit 8631e0fa0b — fix(anatomy): scope doctor --structure to declared trees + prune vendor dirs in reuse nudge
- 2026-06-13 [claude]: Complete. Anatomy map (AnatomyEntry→aggregator→anatomy-map fragment in AGENTS.md), cos doctor --structure (scoped to dec
