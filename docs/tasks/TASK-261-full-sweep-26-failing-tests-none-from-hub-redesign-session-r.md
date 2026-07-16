---
id: TASK-261
title: "Full-sweep: 26 failing tests (none from hub-redesign session) \u2014 re-run clean after concurrent work settles"
swimlane: core
kind: bug
epic: null
labels: [ready]
status: archive
priority: P2
appetite: 1d
created: 2026-06-08
started: 2026-06-08
completed: 2026-06-08
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-261: Full-sweep: 26 failing tests (none from hub-redesign session) — re-run clean after concurrent work settles

**Outcome (one sentence):** Bring `pytest tests/ -q` back to green by fixing the 20 persistent failures left by other sessions' landed commits (regen derived artifacts, fix stale tests, reconcile hook-test expectations) — none of which originate from this session's 11 hub-redesign commits.

## Read First
- tests/test_skill_registry.py + tests/test_skill_frontmatter.py — likely a single skill root-cause (frontend-design).
- tests/test_manifest_fresh.py + tests/test_panel_isolation.py — derived-artifact + stale-test drift.
- docs/engineering/hub-architecture.md — Hub contract.

## Repro Steps
1. `uv run --extra rag pytest tests/ -q` on the current tree.
2. Observe 20 failures across test_branding, test_doctor (4), test_expected_tables_fresh, test_hooks_new (2), test_hooks_phase_e (4), test_hooks_phase_m (1), test_manifest_fresh, test_panel_isolation, test_persona_integration, test_skill_frontmatter[frontend-design], test_skill_registry (2), test_sync_all.
3. Confirmed persistent across two runs (6 golden_parity failures self-resolved as concurrent work settled).

## Threat Model
n/a (test-health task; no new attack surface).

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the 20 failing tests, **When** their root causes are fixed (regen + test reconciliation), **Then** each passes.
- **Given** the fixes, **When** the touched verification-matrix suites re-run, **Then** no new regression appears.

## Work Log
- 2026-06-08 [claude]: Fixed the one STABLE root cause: skill-frontmatter cluster (28b5f2af) — greens test_skill_registry+skill_frontmatter. Re
- 2026-06-08 [claude]: Status transitioned to complete via cos task-done.
