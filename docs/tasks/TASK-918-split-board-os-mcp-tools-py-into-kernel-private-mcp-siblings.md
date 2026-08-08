---
id: TASK-918
title: "Split board_os/mcp_tools.py into kernel + private _mcp_* siblings"
swimlane: "board_os"
kind: refactor
epic: null
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-08-08
started: 2026-08-08
completed: 2026-08-08
agent_session: ses-claude-20260807-224955-abc1
depends_on: []
blocked_by: []
references: []
---
# TASK-918: Split board_os/mcp_tools.py into kernel + private _mcp_* siblings

**Outcome (one sentence):** mcp_tools.py drops 3228 to ~640 lines as the single public/monkeypatch surface; five _mcp_* siblings hold the implementation; board suite green.

## Read First
- src/core/board_os/mcp_tools.py
- src/core/graph_os/tools/graph.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the split **When** the board_os matrix suite runs **Then** all tests pass with unchanged monkeypatch sites
- **Given** consumers importing board_os.mcp_tools **When** they access any cos_* tool or _helper **Then** the name resolves via the kernel re-exports

## Work Log
- 2026-08-08 [claude]: Edit _mcp_shared.py
- 2026-08-08 [claude]: Edit fix_doctor_cycle.py
- 2026-08-08 [claude]: Edit _doctor_shared.py
- 2026-08-08 [claude]: commit 141e1029ec — refactor(tests): split test_cli.py into _cli_suite part modules
- 2026-08-08 [claude]: Status transitioned to complete via cos task-done.
