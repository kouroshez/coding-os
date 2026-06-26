---
id: TASK-594
title: "Harden TASK-590/591 per ultra-review: re-open stamp refresh, non-ASCII reason, doc drift, glob order"
swimlane: infra
kind: bug
epic: git-foundation-hardening
labels: [pr-mode, test-governance, code-review, ready]
status: complete
priority: P2
appetite: 1d
created: 2026-06-26
started: 2026-06-26
completed: 2026-06-26
agent_session: ses-claude-20260625-235014-c028
depends_on: []
blocked_by: []
references: []
---
# TASK-594: Harden TASK-590/591 per ultra-review: re-open stamp refresh, non-ASCII reason, doc drift, glob order

**Outcome (one sentence):** Fix the CONFIRMED in-scope findings from the ultra code-review (workflow w9hzbmkto, 34 agents) of the 590/591 diff — refresh the worktree owner stamp on idempotent re-open, make _lock_owner_alive robust to a porcelain-C-quoted non-ASCII host (match owner=<pid> only), make _owner_pid_host's glob deterministic, and realign test-governance.md §3 + the stale test name with the new lock model.

## Read First
- src/cli/pr_commands.py
- src/core/hooks/test-governor.sh
- docs/engineering/test-governance.md
- tests/test_cli.py
- tests/test_test_governor.py

## Repro Steps
1) A worktree lock whose reason contains a non-ASCII host makes `git worktree list --porcelain` emit a C-quoted line (`locked "pr-mode session ses owner=123@caf\303\251-host"`) so `owner=(\d+)@(\S+)` captures a corrupted host, _lock_owner_alive returns False, and a live worktree becomes reapable. 2) `git worktree lock` no-ops on an already-locked tree, so an idempotent re-open never refreshes the owner pid. 3) test-governance.md §3 still documents `pgrep -f pytest` + the removed 120s grace + a 4-field lock (no agent_pid).

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** a non-ASCII hostname, **When** the reaper reads a stamped lock reason, **Then** _lock_owner_alive parses owner=<pid> and keeps a live same-host owner (no false reap). **Given** an idempotent re-open by a restarted agent, **When** pr open runs, **Then** the lock reason carries the current live pid (unlock+relock). **Given** a reader of test-governance.md §3, **Then** it describes agent_pid + kill -0 + no host-global pgrep. Verify: uv run pytest tests/test_cli.py::TestCosPr -q + tests/test_test_governor.py -q + make verify-hooks + make docs-lint all green.

## Work Log
- 2026-06-26 [claude]: Edit pr_commands.py
- 2026-06-26 [claude]: Edit pr_commands.py
- 2026-06-26 [claude]: Edit pr_commands.py
- 2026-06-26 [claude]: Edit test-governance.md
- 2026-06-26 [claude]: Edit test-governance.md
- 2026-06-26 [claude]: Edit test_test_governor.py
- 2026-06-26 [claude]: Edit test_test_governor.py
- 2026-06-26 [claude]: Edit test_cli.py
- 2026-06-26 [claude]: commit 8c43b75057 — fix(pr): harden owner-stamp liveness — refresh on re-open, parse pid past a quoted host
- 2026-06-26 [claude]: Applied 5 CONFIRMED in-scope review fixes. Key deliberation: dropped the @host from _lock_owner_alive's regex (match…
