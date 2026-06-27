---
id: TASK-600
title: "coexistence: root-containment collision + longest-pattern owner match (fixes shipped t3-style)"
swimlane: cli
kind: bug
epic: stack-factory-v2
labels: [ready]
status: icebox
priority: P2
appetite: 2d
created: 2026-06-27
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-600: coexistence: root-containment collision + longest-pattern owner match (fixes shipped t3-style)

**Outcome (one sentence):** Nested-root stack collisions — shipped today as the t3-style preset (typescript-plain root `src` contains nextjs root `src/frontend`, both owning src/frontend/**/*.ts) — are detected and relocated/rejected, and owner resolution becomes specificity-deterministic instead of stack-list-order-arbitrary.

## Read First
- src/cli/stack_registry.py
- src/core/hooks/_enforce_scaffold_boundary.py
- src/templates/_presets/t3-style.yaml

## Repro Steps
cat src/templates/_presets/t3-style.yaml shows stacks: [nextjs, typescript-plain]; grep root: src/templates/typescript-plain/stack.yaml (src) vs src/templates/nextjs/stack.yaml (src/frontend); src/cli/stack_registry.py:469 service_relocations keys exact roots only so the nest is undetected; src/core/hooks/_enforce_scaffold_boundary.py:33-39 first-match-in-list wins with no longest-pattern tiebreak.

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** two installed stacks whose roots nest (A is a path-prefix of B), **When** service_relocations runs, **Then** the overlap is detected and both are relocated to src/services/<id>/ or rejected with a clear message (today only exact-equal roots trigger).
**Given** two scaffold-boundary file_patterns match one path, **When** the boundary hook and enforce-skill matcher resolve the owner, **Then** the longest (most specific) pattern wins (today first-match-in-stack-list).
**Then** `make verify-hooks` and `uv run pytest tests/test_cli.py -q` are green.

## Work Log
