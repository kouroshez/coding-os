---
id: TASK-133
title: "Scaffold self-consistency guards \u2014 dimension\u2192doc guard test, go-fiber dangling ref, multi-stack doc-collision namespacing"
swimlane: templates
kind: bug
epic: doc-system
labels: [docs-system, templates, multi-stack, audit-d2-f1, ready]
status: complete
priority: P2
appetite: 1d
created: 2026-06-05
started: 2026-06-06
completed: 2026-06-06
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-133: Scaffold self-consistency guards — dimension→doc guard test, go-fiber dangling ref, multi-stack doc-collision namespacing

**Outcome (one sentence):** A stack can no longer ship a Read List pointing at a non-existent doc, nor silently overwrite another stack's doc: a test asserts every stack's dimensions[].read_files resolves in that stack+_base scaffold (D2-F1), go-fiber's dangling docs/playbooks/security-review.md ref is fixed (D2-F2), and the colliding accessibility-checklist.md is namespaced per platform (accessibility-web / accessibility-mobile) with a collision test (D2-F4).

## Read First
- docs/tasks/audits/audit-doc-system-2026-06-05.md
- src/templates/go-fiber/stack.yaml
- tests/test_template_scaffold.py

## Repro Steps
1. `grep security-review src/templates/go-fiber/stack.yaml` → the "Middleware / auth" dimension lists docs/playbooks/security-review.md, but `find src/templates/go-fiber src/templates/_base -name security-review.md` returns nothing — a dangling Read List entry.
2. nextjs and react-native BOTH ship docs/engineering/accessibility-checklist.md; `cos add-stack` of a second stack overwrites the first's copy (collision, data loss).
Expected: every dimension read_file resolves; platform a11y docs are namespaced so two stacks co-install cleanly.
Actual: go-fiber ref dangles; a11y filenames collide.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** every stack.yaml's dimensions[].read_files and the a11y docs of nextjs + react-native
- **When** the scaffold guard test runs
- **Then** each read_file resolves in that stack's or _base's scaffold (go-fiber's dangling security-review ref removed); accessibility-checklist.md is renamed accessibility-web.md (nextjs) / accessibility-mobile.md (react-native) with all stack.yaml refs updated; a co-install collision test passes — verified by test-template-scaffold + regen-rules.

## Work Log
- 2026-06-07 [claude]: D2-F2: dropped go-fiber's dangling docs/playbooks/security-review.md from the Middleware/auth dimension (fiber-rules.md
- 2026-06-07 [claude]: committed 0c9adc96: src/core/rules/dimension-registry.md, src/templates/_base/dimension-registry.template.md, src/templa
