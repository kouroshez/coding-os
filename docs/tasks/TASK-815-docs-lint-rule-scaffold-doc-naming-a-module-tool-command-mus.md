---
id: TASK-815
title: "docs-lint rule \u2014 scaffold doc naming a module tool/command must carry the matching module tag (F-H / rank 5)"
swimlane: core
kind: feature
epic: modularity-completion
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-07-16
started: 2026-07-16
completed: 2026-07-16
agent_session: ses-claude-20260716-001729-7bd4
depends_on: []
blocked_by: []
references: []
---
# TASK-815: docs-lint rule — scaffold doc naming a module tool/command must carry the matching module tag (F-H / rank 5)

**Outcome (one sentence):** A docs-lint rule keeps module-tag coverage tracking the registry automatically: any scaffold doc that names a cos_<family> tool or a module-owned slash command without a matching file/block module tag fails lint, so init-time orphan references to disabled-module capabilities cannot silently accrue.

## Read First
- src/cli/main.py
- src/core/subsystems.yaml
- Makefile

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** a scaffold doc naming /memory-search (memory-owned) or cos_graph_* (graph-owned) with no matching `| module:` header or `<!-- if-module -->` block, **When** make docs-lint runs, **Then** it flags the doc with the missing tag; a correctly-tagged or untagged-non-module doc passes.
Checklist:
- [ ] Find the docs-lint entrypoint (make docs-lint target) + extend or add a checker.
- [ ] Build the module->tools/commands map from subsystems.yaml (reuse the loader, not a hardcode).
- [ ] Scan src/templates/**/scaffold/docs/**.md: if a doc names a module-owned tool family or slash command, require a matching module tag (file-level or block-level covering that mention).
- [ ] Tolerate cross-cutting/always-on tools (kernel) — no tag required.
- [ ] Fix the existing orphan (workflow-guide.md names /memory-search untagged) as part of this.
- [ ] Tests: planted untagged module-tool doc fails; tagged passes.
- [ ] Verify: make docs-lint + uv run pytest for the linter test.

## Work Log
- 2026-07-16 [claude]: Edit audit_scaffold_module_tags.py
- 2026-07-16 [claude]: Edit audit_scaffold_module_tags.py
- 2026-07-16 [claude]: Edit workflow-guide.md
- 2026-07-16 [claude]: Edit workflow-guide.md
- 2026-07-16 [claude]: Edit Makefile
- 2026-07-16 [claude]: Edit audit_scaffold_module_tags.py
- 2026-07-16 [claude]: Edit test_scaffold_module_tags.py
- 2026-07-16 [claude]: Added src/scripts/dev/audit_scaffold_module_tags.py — flags a scaffold doc naming a module-owned SLASH COMMAND…
- 2026-07-16 [claude]: commit 15543657cf — feat(docs): lint scaffold docs for untagged module-owned slash commands (F-H)
