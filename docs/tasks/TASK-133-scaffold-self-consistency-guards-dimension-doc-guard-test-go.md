---
id: TASK-133
title: "Scaffold self-consistency guards — dimension→doc guard test, go-fiber dangling ref, multi-stack doc-collision namespacing"
swimlane: templates
kind: bug
epic: doc-system
labels: [docs-system, templates, multi-stack, audit-d2-f1, ready]
status: icebox
priority: P2
appetite: "1d"
created: 2026-06-05
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-133: Scaffold self-consistency guards — dimension→doc guard test, go-fiber dangling ref, multi-stack doc-collision namespacing

**Outcome (one sentence):** A stack can no longer ship a Read List pointing at a non-existent doc, nor silently overwrite another stack's doc: a test asserts every stack's dimensions[].read_files resolves in that stack+_base scaffold (D2-F1), go-fiber's dangling security-review.md ref is fixed (D2-F2), and platform-specific colliding docs (accessibility-checklist.md) are namespaced (accessibility-web/-mobile) with a collision test for any two co-installed stacks (D2-F4).

## Read First
- docs/tasks/audits/audit-doc-system-2026-06-05.md
- tests/test_template_scaffold.py
- src/cli/main.py
- src/templates/go-fiber/stack.yaml

## Repro Steps
1. (fill in: exact steps to reproduce)
2. ...
Expected: ...
Actual: ...

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** ...
- **When** ...
- **Then** ...

## Work Log
