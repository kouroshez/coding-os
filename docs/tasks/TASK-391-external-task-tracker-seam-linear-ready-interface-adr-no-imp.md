---
id: TASK-391
title: "External task-tracker seam \u2014 Linear-ready interface ADR (no implementation)"
swimlane: "board_os"
kind: docs
epic: G-modularity
labels: [backlog, onboarding-program, ready]
status: icebox
priority: P3
appetite: 1d
created: 2026-06-11
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-391: External task-tracker seam — Linear-ready interface ADR (no implementation)

**Outcome (one sentence):** A single ADR at docs/architecture/adr/0006-external-task-tracker-seam.md defines the interface seam (the `tasks` subsystem `cos_task_*` surface + the `module_disabled` fallback) an external tracker must satisfy when board_os's tasks module is off — contract only, no implementation.

## Read First
- src/core/board_os/mcp_tools.py (the cos_task_* tool surface to abstract behind the seam)
- src/core/subsystems.yaml (the `tasks` module declaration + depends_on: [docs])
- src/core/thinking_os/tools/_shared.py (`_gated_module` → `module_disabled` fallback)
- docs/governance/adr-task-id-allocator-seam.md (existing external_ref seam to reuse, not duplicate)
- docs/governance/task-lifecycle.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the numbered-ADR convention, **When** the task closes, **Then** exactly one new file docs/architecture/adr/0006-external-task-tracker-seam.md exists (next free number after 0005), opens with the standard SSOT doc-header comment (per docs/governance/docs-system.md) plus a Status line (`Proposed`/`Accepted` + date + TASK-391), and is registered in docs/architecture/adr/00-index.md.
- **Given** the ADR is contract-only, **When** it is reviewed, **Then** it carries Context / Decision / Consequences / Alternatives sections, and the Decision names only the real seam: the `tasks` module in src/core/subsystems.yaml, the `cos_task_*` + `cos_work_log_append` tools, and the `module_disabled` category emitted by `_gated_module` — no invented tool or field names.
- **Given** the Linear-ready framing, **When** the Decision is read, **Then** it lists the minimum adapter interface against the real surface (at least create / move / show / board-list / append-work-log, each mapped to its tool in src/core/board_os/mcp_tools.py) and reuses the `external_ref` linkage from docs/governance/adr-task-id-allocator-seam.md instead of inventing a parallel id scheme.
- **Given** no-implementation scope, **When** the diff is inspected, **Then** `git diff --name-only` touches only docs/architecture/adr/ (the new ADR + 00-index.md) and this task file — zero changes under src/** and zero new cos_* tool definitions.
- **Given** the file-first decision, **When** Consequences/Alternatives is read, **Then** it explicitly reconciles with docs/architecture/adr/0005-board-os-file-first-scrumban.md: the seam does NOT make board_os DB-first, and disabling `tasks` removes the native board rather than relocating user task files.
- **Given** the docs matrix row, **When** `make docs-lint` runs, **Then** it exits OK with every internal link in the new ADR resolving.

## Rollback
Delete docs/architecture/adr/0006-external-task-tracker-seam.md and revert its line in docs/architecture/adr/00-index.md; docs-only, so no runtime or schema state changes.

## Work Log
