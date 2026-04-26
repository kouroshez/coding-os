---
id: TASK-078
title: "Graph: Rename orchestrator (plan → preview diff → apply) via Hub UI"
swimlane: graph_os
kind: feature
epic: graph_os-the upstream scope-resolution implementation
labels: [hub, graph, rename, P2-ux-parity]
status: icebox
priority: P2
appetite: "6h"
created: 2026-04-24
started: null
completed: null
agent_session: null
depends_on: [TASK-077]
blocked_by: []
references: []
---

# TASK-078: Graph — Rename orchestrator (plan → preview diff → apply)

**Outcome (one sentence):** Right-click rename on a node in the Graph tab opens a three-step flow — Plan, Preview (diff with `files_affected + total_edits + confidence split graph_edits vs text_search_edits`), Apply — driven by the existing `cos_graph_rename_plan` MCP tool plus a new `cos_graph_rename_apply`.

## Read First

- [core/graph_os/tools/](../../core/graph_os/tools/) — `cos_graph_rename_plan` (already returns plan, confidence split).
- [docs/engineering/rename-workflow.md](../../docs/engineering/rename-workflow.md) — canonical workflow this UI must honour.
- [core/web/ui/src/features/graph/](../../core/web/ui/src/features/graph/) — host location for new RenameDialog.
- [core/graph_os/extractors/code_python.py](../../core/graph_os/extractors/code_python.py) + [code_ts.py](../../core/graph_os/extractors/code_ts.py) — the precise-edits source; anything not covered falls back to text-search with lower confidence.

## Acceptance (G/W/T) — *this IS the Definition of Done*

- **Given** a selected node in the Graph tab
  **When** the user right-clicks and chooses "Rename…"
  **Then** a modal opens with the current name pre-filled, a short validation note ("must match /^[A-Za-z_][A-Za-z0-9_]*$/"), and a "Plan" button.
- **Given** a valid new name
  **When** the user clicks "Plan"
  **Then** the UI calls `POST /api/p/<slug>/graph/rename/plan` and shows: total files affected, total edits, and a confidence split bar (e.g. `82% graph_edits · 18% text_search_edits`).
- **Given** the plan
  **When** the user clicks "Preview"
  **Then** a diff viewer opens with one unified diff per affected file, each edit tagged `graph` (green badge) or `text-search` (amber badge with a click-to-see-why tooltip).
- **Given** the preview
  **When** the user clicks "Apply"
  **Then** the orchestrator writes all edits atomically via a single transactional pass, re-triggers `cos graph-reindex` for affected files only, and shows a success toast with "View work-log entry" linking to an auto-created board note under the originating task (if any).
- **Given** any failure (write conflict, reindex error)
  **When** Apply is in-flight
  **Then** all partial writes roll back via the session-scoped undo buffer, and the UI surfaces the error from the `fail()` envelope category.
- **Tests:** `tests/test_rename_orchestrator.py` covers plan/preview/apply success + rollback; Playwright `e2e/graph-rename.spec.ts` covers the UI flow + confidence badges.

## Implementation Notes

1. New MCP tool `cos_graph_rename_apply(plan_id, confirm=True) -> ok({applied_edits, reindexed_files})` with proper envelope (fail categories: `validation`, `conflict`, `transient` for FS races).
2. New routes `POST /api/p/<slug>/graph/rename/plan` and `POST /api/p/<slug>/graph/rename/apply` thin-wrap the MCP tools.
3. UI component: `features/graph/RenameDialog.tsx` with three inner states (plan → preview → apply-result); use `@uiw/react-md-editor` or reuse whatever diff lib the Cognition trace replay already pulls in.
4. Keep **text-search fallback edits behind an explicit checkbox** — default is "graph-only" for safety; the checkbox label includes the confidence percentage to make the trade-off visible.
5. Apply step MUST produce a stable commit message suggestion (`refactor(rename): Foo → Bar (N files, M edits)`) copy-pasteable from the success toast.

## Dependencies

- **Depends on:** TASK-077 (multi-language) — single-language rename is not a credible feature.
- **Unblocks:** none directly; closes the P2 UX parity triad.

## Work Log
