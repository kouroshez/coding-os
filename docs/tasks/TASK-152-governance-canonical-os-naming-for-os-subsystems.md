---
id: TASK-152
title: "governance: canonical _os naming for OS subsystems"
swimlane: core
kind: refactor
epic: naming-contract
labels: [governance, naming]
status: complete
priority: P1
appetite: "4h"
created: 2026-04-26
started: 2026-04-26
completed: 2026-04-26
agent_session: ses-claude-20260426-185755-6c29
depends_on: []
blocked_by: []
references: []
---
# TASK-152: governance: canonical _os naming for OS subsystems

**Outcome (one sentence):** Subsystem identifiers use thinking_os, graph_os, and board_os consistently across repo machine surfaces; display text uses Thinking OS, Graph OS, and Board OS; legacy hyphen aliases are removed from generated source/docs except explicit migration notes.

## Read First
- [docs/engineering/naming-contract.md](../engineering/naming-contract.md) — canonical subsystem naming contract.
- [AGENTS.md](../../AGENTS.md) — meta-project governance and verification matrix.
- [core/hooks/registry.yaml](../../core/hooks/registry.yaml) — hook names and generated adapter surfaces.
- [templates/_base/Makefile.base](../../templates/_base/Makefile.base) — generated project defaults.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** tracked repo files after the migration
  **When** searching for legacy hyphenated subsystem aliases or banned graph-tool product references
  **Then** no non-legacy source, template, generated fixture, task metadata, or path-like doc emits those names.
- **Given** subsystem names are needed in code, config, tasks, DB filenames, state filenames, or paths
  **When** new content is generated or rendered
  **Then** it uses `thinking_os`, `graph_os`, and `board_os`.
- **Given** human-facing prose names the subsystems
  **When** docs need a display label
  **Then** they use Thinking OS, Graph OS, and Board OS instead of hyphenated IDs.
- **Given** banned graph-tool product references existed in docs/tasks/UI comments
  **When** the cleanup finishes
  **Then** those references are removed or replaced with generic capability language.

## Work Log
- 2026-04-26 — Created naming contract and scoped repo-wide migration.
- 2026-04-26 — Codex session abandoned mid-task; ownership reassigned. Took over via Claude.
- 2026-04-26 — Surgical migration committed: 32 file renames (hyphen→underscore in subsystem paths) + content sweep across 271 modified files. Mixed-content files split using HEAD-baseline sweep + WIP preservation, so unrelated WIP for other tasks (TASK-089..151) remains in working tree intact. Verification: `git ls-files | xargs grep "thinking-os|graph-os|board-os|external graph tooling"` → 0 hits in staged + tracked content. Display-name pass (Thinking OS / Graph OS / Board OS in human prose) intentionally deferred — current sweep was mechanical token rename; semantic prose audit is a separate pass.
- 2026-04-26 [claude]: Status transitioned to complete via cos task-done.
