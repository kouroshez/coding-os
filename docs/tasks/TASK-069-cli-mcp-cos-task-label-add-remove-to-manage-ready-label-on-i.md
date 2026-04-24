---
id: TASK-069
title: "CLI + MCP: cos task-label add/remove to manage ready label on icebox tasks"
swimlane: board-os
kind: feature
epic: hub-ux-hardening
labels: [hub, cli, mcp]
status: icebox
priority: P1
appetite: "1h"
created: 2026-04-24
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: [TASK-068]
---

# TASK-069: CLI + MCP — `cos task-label` add/remove

**Outcome (one sentence):** Agents and humans promote icebox tasks to pickup-ready via `cos task-label <TASK-ID> --add ready` (and remove via `--remove ready`), with an MCP tool `cos_task_label` at parity, so the green READY pill landed by TASK-068 has a canonical way to be toggled without hand-editing frontmatter.

## Read First

- [cli/board_commands.py](../../cli/board_commands.py) — where `task-*` click commands live (lines ~200–400).
- [core/board_os/parser.py](../../core/board_os/parser.py) — frontmatter parser that reads / writes the `labels: [...]` array.
- [core/board_os/workflow.py](../../core/board_os/workflow.py) — state transitions; label edits are lighter but must follow the same audit path.
- [core/board_os/mcp_tools.py](../../core/board_os/mcp_tools.py) — add the new MCP tool next to `cos_task_move`, `cos_task_pick`.
- **TASK-068** (already `complete`) — renders the pill; this task adds the lever.

## Acceptance (G/W/T) — *this IS the Definition of Done*

- **Given** an icebox task without label `ready`
  **When** the user runs `cos task-label TASK-057 --add ready`
  **Then** the frontmatter `labels:` array gets `ready` appended (idempotent — running twice does not duplicate), the command exits 0, and `cos board` shows the green READY pill on TASK-057.
- **Given** a task with label `ready`
  **When** `cos task-label TASK-057 --remove ready`
  **Then** the label is removed, idempotent, pill disappears.
- **Given** a non-existent label (e.g. `--add foo`)
  **When** called
  **Then** the command succeeds and adds `foo` (labels are free-form per Rule 14). Only `ready` has UI meaning today.
- **Given** the MCP tool
  **When** an agent calls `cos_task_label(task_id="TASK-057", add=["ready"])`
  **Then** the envelope returns `ok({task_id, labels_before, labels_after})`.
- **Given** a task whose file is missing or whose frontmatter is malformed
  **When** called
  **Then** envelope returns `fail("not_found", …)` or `fail("validation", …)` respectively — no partial write.
- **Tests:** `core/board_os/tests/test_label_command.py` covers add/remove idempotency, envelope categories, and frontmatter round-trip (YAML quoting preserved).

## Implementation Notes

1. New CLI: `cos task-label TASK-NNN [--add L1,L2] [--remove L3,L4]` — at least one of `--add` / `--remove` required.
2. Write path:
   - Parse existing frontmatter.
   - Apply `add` (dedup preserving order) then `remove`.
   - If nothing changed, skip the write and print "no change".
   - Atomic write: temp file + `os.replace`.
3. MCP tool: `cos_task_label(task_id, add=[], remove=[]) -> ok({task_id, labels_before, labels_after, changed: bool})`. Wrap with `@safe_tool`.
4. Audit: append a row in `task_status_history` with `reason: "label edit: +ready"` so the SSE stream surfaces the event (agent attribution works without a new table).
5. Edge case: when `--add ready` moves a task into "pickup-ready" eligibility, consider whether we should also auto-remove `status=icebox`. **Decision:** NO — status and label are orthogonal axes; board UI rules, not this CLI, decide presentation.

## Dependencies

- **Depends on:** none (TASK-068 already landed the UI side).
- **Unblocks:** TASK-057 / TASK-059 / TASK-060 can now be "promoted" cleanly when the hub is ready to pick them up.

## Work Log
