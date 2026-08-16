---
id: TASK-997
title: "Stack-rule refresh calls an untouched rule user-edited when the mirror predates it"
swimlane: infra
kind: bug
epic: null
labels: [ready]
status: complete
priority: P1
appetite: 1d
created: 2026-08-16
started: 2026-08-16
completed: 2026-08-16
agent_session: ses-claude-20260814-120316-413b
depends_on: []
blocked_by: []
references: []
---
# TASK-997: Stack-rule refresh calls an untouched rule user-edited when the mirror predates it

**Outcome (one sentence):** A rule already identical to its template is silent on cos update — neither refreshed nor reported as an edit — so the only files named are ones that genuinely moved or genuinely diverged.

## Read First
- src/cli/_init_scaffold.py
- tests/test_stack_rule_refresh.py

## Repro Steps
In this repo `cos update --dry-run` prints "Kept your edited stack rule meta-graph-first.md" for all four meta-* rules, each of which is byte-identical to its current template — the mirror under .coding-os/src/templates/meta/rules/ is frozen at 2026-05-14. Two rules appear in both the kept and the would-refresh lists across agents.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** an installed rule byte-identical to the current template but differing from a stale mirror, **When** cos update runs, **Then** it says nothing about that file.
- **Given** the same tree, **When** cos update runs, **Then** no file name appears in both the refreshed and the kept list.

## Work Log
- 2026-08-16 [claude]: Edit _init_scaffold.py
- 2026-08-16 [claude]: Edit repro_multiagent.py
- 2026-08-16 [claude]: Edit test_stack_rule_refresh.py
- 2026-08-16 [claude]: commit 1e3f105c1a — fix(cli): stop reporting an up-to-date stack rule as a user edit
- 2026-08-16 [claude]: Found by running cos update --dry-run in this repo rather than trusting the unit tests: all four meta-* rules were…
- 2026-08-16 [claude]: Found by running cos update --dry-run in this repo rather than trusting the unit tests: all four meta-* rules were…
- 2026-08-16 [claude]: Edit dry-run-in-repo-before-trusting-units.md
- 2026-08-16 [claude]: Edit probe.py
- 2026-08-16 [claude]: Edit MEMORY.md
- 2026-08-16 [claude]: Status transitioned to complete via cos task-done.
