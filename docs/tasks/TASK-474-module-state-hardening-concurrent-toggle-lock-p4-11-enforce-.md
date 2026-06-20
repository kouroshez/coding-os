---
id: TASK-474
title: "Module-state hardening \u2014 concurrent-toggle lock (P4-11) + enforce-skill meta-scope (P4-14/15) + corrupt-state visibility (P4-12)"
swimlane: infra
kind: bug
epic: null
labels: [modularity, hooks, audit-pass4, ready]
status: icebox
priority: P2
appetite: 1d
created: 2026-06-20
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-474: Module-state hardening — concurrent-toggle lock (P4-11) + enforce-skill meta-scope (P4-14/15) + corrupt-state visibility (P4-12)

**Outcome (one sentence):** Module-state writes are concurrency-safe (per-pid temp + advisory flock over the RMW), the enforce-skill graph-explorer guard no longer leaks the meta-repo-only block onto consumers (meta-scope gate) and self-skips when the graph module is disabled, and a corrupt subsystems-state.json surfaces a doctor WARN instead of silently failing open to all-enabled.

## Read First
- src/cli/subsystems.py
- src/core/hooks/enforce-skill.sh
- src/cli/doctor.py
- src/core/subsystems.yaml

## Repro Steps
subsystems.py:177-190 set_module_enabled is an unlocked read-modify-write with a fixed .json.tmp name (two writers → one toggle silently lost + torn write). enforce-skill.sh:84 `*core/*.py` substring matches /myapp/src/core/service.py on any consumer (hook symlinked verbatim). subsystems.py:85-87 _read_disabled catches corruption → returns set() (all-enabled) at logger.debug; next toggle persists the loss; doctor reads through it → PASS.

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** two processes toggling different modules from a shared start state, a consumer with a core/ dir editing core/x.py, and a truncated subsystems-state.json **When** the toggles race / the consumer write is attempted / doctor runs **Then** both toggles persist (no silent lost-update), the consumer write is NOT blocked demanding graph-explorer (meta-scope gate), and `cos doctor` emits a state_integrity WARN naming the corruption; AND make verify-hooks + the module/cli matrix suites pass.

## Work Log
