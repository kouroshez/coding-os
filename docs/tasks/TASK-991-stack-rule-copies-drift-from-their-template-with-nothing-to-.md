---
id: TASK-991
title: "Stack rule copies drift from their template with nothing to detect it"
swimlane: cli
kind: bug
epic: honest-benchmarks
labels: [ready]
status: in_progress
priority: P1
appetite: 1d
created: 2026-08-15
started: 2026-08-15
completed: null
agent_session: ses-claude-20260814-120316-413b
depends_on: []
blocked_by: []
references: []
---
# TASK-991: Stack rule copies drift from their template with nothing to detect it

**Outcome (one sentence):** A stack rule that has drifted from the template it was scaffolded from is reported by `cos doctor`, so an edit to `src/templates/<stack>/rules/` can no longer look propagated when it has reached no installed project.

## Read First
- src/cli/_doctor_stacks.py
- src/cli/_update_manifest.py
- src/cli/_init_scaffold.py

## Repro Steps
Verified by executing: replaced `.claude/rules/meta-graph-first.md` with a stale marker, ran `cos update`, and the marker survived — `cos update` refreshes symlinked core rules but never the per-stack rule copies, which `_update_manifest.py:304` deliberately excludes as user-owned. `cos update --help` nonetheless promises it "applies any new hooks/skills/rules/commands". The corrected graph-first rule committed in 0d319d0c therefore reached zero consumers, and `third-party-token-bench.md` cites the stale rendered copy as "the rule these numbers back". No check reports the divergence.

## Acceptance (G/W/T) — *this IS the Definition of Done*

- **Given** an installed stack rule whose content differs from its template source, **When** `cos doctor` runs, **Then** it reports the drift by name rather than passing silently.
- **Given** a stack rule the user has deliberately customised, **When** the check reports it, **Then** it warns rather than fails — ownership stays with the user and the check only makes the divergence visible.
- **Given** a project with no stacks, or an adapter with no rules dir, **When** the check runs, **Then** it passes with a stated reason instead of erroring.
- **Given** the check, **When** its test runs against a deliberately drifted copy, **Then** it is red before the fix and green after.

## Work Log
- 2026-08-15 [claude]: Edit _doctor_stacks.py
- 2026-08-15 [claude]: Edit test_doctor_stack_rules_fresh.py
- 2026-08-15 [claude]: Edit test_doctor_stack_rules_fresh.py
- 2026-08-15 [claude]: Added the stack.rules_fresh doctor check comparing each installed per-stack rule against its template source. It…
