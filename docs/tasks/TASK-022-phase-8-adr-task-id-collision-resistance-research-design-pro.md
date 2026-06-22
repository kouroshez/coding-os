---
id: TASK-022
title: "Phase 8 ADR: task ID collision resistance research + design proposal"
swimlane: docs
kind: docs
epic: null
labels: [adr, task-id, oss]
status: archive
priority: P2
appetite: "1h"
created: 2026-05-23
started: 2026-05-23
completed: 2026-05-23
agent_session: ses-claude-20260523-010526-e647
depends_on: []
blocked_by: []
references:
  - docs/governance/adr-task-id-collision-resistance.md
  - src/core/board_os/mcp_tools.py
  - src/core/board_os/config.py
---
# TASK-022: Phase 8 — task ID collision ADR

**Outcome (one sentence):** Publish [docs/governance/adr-task-id-collision-resistance.md](../governance/adr-task-id-collision-resistance.md) — research synthesis + 5 options + recommended layered path so the project owner can make an informed choice before any code lands.

This is **design / docs only**. No code change. The recommended Option-3 path (GitHub Issues as allocator) lands in a follow-up task once the owner approves the strategy.

## Read First
- [docs/governance/adr-task-id-collision-resistance.md](../governance/adr-task-id-collision-resistance.md) — the deliverable
- [src/core/board_os/mcp_tools.py](../../src/core/board_os/mcp_tools.py) — `_next_task_id` (current allocator, lines 73-92)
- [src/core/board_os/config.py](../../src/core/board_os/config.py) — `ScrumbanConfig` (the dataclass that would gain `task_id_prefix`)

## Acceptance — *this IS the Definition of Done*
- ADR published with 5 options compared, recommendation stated, migration plan, open questions.
- `make docs-lint` clean.
- No code change in this task (config plumbing + GitHub integration are follow-ups).

## Work Log
- 2026-05-23 — published ADR with 5 options (status quo · project key · GitHub Issues · ULID · hybrid), recommended layered path (1. add `task_id_prefix` config seam · 2. GitHub Issues as allocator · 3. optional ULID fallback). No code change in this task. `make docs-lint` clean.
- 2026-05-23 [claude]: Status transitioned to complete via cos task-done.
