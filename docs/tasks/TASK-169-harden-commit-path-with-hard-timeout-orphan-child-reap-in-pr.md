---
id: TASK-169
title: "Harden commit path with hard timeout + orphan-child reap in pre-commit"
swimlane: core
kind: bug
epic: agent-hub
labels: [ready]
status: archive
priority: P1
appetite: "4h"
created: 2026-06-05
started: 2026-06-05
completed: 2026-06-05
agent_session: ses-claude-20260605-183120-db30
depends_on: []
blocked_by: []
references: []
---
# TASK-169: Harden commit path with hard timeout + orphan-child reap in pre-commit

**Outcome (one sentence):** A hung or orphaned pre-commit child can never stall the next commit — the whole batch runs under a portable hard timeout that reaps the process subtree, fail-open with a loud warning.

## Read First
- docs/engineering/agent-hub-orchestration.md
- src/scripts/_pre_commit_body.sh
- src/core/hooks/_helpers/pre_commit_batch.py

## Repro Steps
1. A pre-commit hook child blocks (busy DB / embedding / MCP) and the per-hook 15s timeout in pre_commit_batch.py is escaped (cumulative runaway or python startup hang).
2. `_pre_commit_body.sh:52` runs `python3 BATCH_HELPER ...` with NO outer timeout/alarm and no orphan cleanup.
Expected: the commit aborts the scan within a bounded time and the next commit is clean.
Actual: the commit hangs indefinitely; orphaned children keep the index/resources busy so the NEXT commit also hangs (the user's "commits get stuck").

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a batch helper that hangs past the timeout
- **When** the pre-commit body runs it via the new reap-timeout wrapper
- **Then** it returns within ~timeout+grace, the hung subtree is killed (no orphans), the commit is allowed with a loud warning, and a bash test asserts the wrapper kills a sleeper and returns promptly. `make verify-hooks` green; `bash -n` clean.

## Work Log
- 2026-06-05 [claude]: Added portable cos_run_with_reap_timeout helper (bash watchdog + recursive pgrep tree-kill; timeout(1)/setsid absent on 
