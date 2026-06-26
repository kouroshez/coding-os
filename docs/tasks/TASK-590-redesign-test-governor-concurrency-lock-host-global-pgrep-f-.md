---
id: TASK-590
title: "Redesign test-governor concurrency lock (host-global pgrep -f pytest is wrong; PID-of-agent fix is also wrong)"
swimlane: infra
kind: bug
epic: git-foundation-hardening
labels: [test-governance, concurrency, split-from-585, ready]
status: complete
priority: P3
appetite: 1d
created: 2026-06-26
started: 2026-06-26
completed: 2026-06-26
agent_session: ses-claude-20260625-235014-c028
depends_on: []
blocked_by: []
references: []
---
# TASK-590: Redesign test-governor concurrency lock (host-global pgrep -f pytest is wrong; PID-of-agent fix is also wrong)

**Outcome (one sentence):** Split out of TASK-585. test-governor.sh decides lock-held via host-global `pgrep -f pytest` (test-governor.sh:118): cross-repo phantom-hold (repo A blocked by repo B's pytest) + false-clear (a `uv run pytest` wrapper / pytest-xdist worker whose argv differs reads as no-pytest → sibling double-runs). The red-team's proposed PID-of-agent fix is ALSO wrong: in Claude Code each panel is a long-lived process, so gating HELD on the agent PID being alive holds the lock for the whole session and blocks every sibling until TTL. The correct fix is a PostToolUse-release leg (PreToolUse acquires the lock, a PostToolUse hook on the pytest Bash command clears it when pytest exits; grace+TTL still bound a crashed session) OR a repo-scoped liveness probe — not a host-global pgrep and not agent-PID. Current behavior errs SAFE (over-holds), so this is correctness/throughput, not a security hole.

## Read First
- src/core/hooks/test-governor.sh
- src/core/hooks/registry.yaml
- docs/engineering/test-governance.md
- src/core/board_os/presence.py

## Repro Steps
1) Write .test-run.lock from repo A with started_ts older than the 120s grace, finish repo A's pytest, start any pytest elsewhere on the host → repo A's test-governor reads HELD=true (cross-repo phantom hold). 2) Run `uv run pytest -p xdist -n4 …`; the workers' argv may not match `pgrep -f pytest` cleanly → a sibling reads the lock free and double-runs. 3) Conceptual: gate HELD on agent PPID pid_alive → the lock never clears within a live Claude panel.

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** repo A's pytest has finished and repo B's is running, **When** repo A checks the lock past the grace window, **Then** repo A is NOT phantom-held by repo B's unrelated pytest. **Given** a `uv run --extra rag pytest` wrapper or pytest-xdist workers, **When** the suite is actively running, **Then** the lock reads HELD (no argv-match false-clear → no sibling double-run). **Given** a long-lived panel that finished its pytest, **When** a sibling wants to run pytest, **Then** the lock is NOT held for the whole session (released when pytest exited, not when the agent process dies). Verify: make verify-hooks green + a new test_hooks case per scenario.

## Work Log
- 2026-06-26 [claude]: commit aa60ad5a0d — chore(golden): refresh hook goldens for cos-env/block-dangerous/session-context drift
- 2026-06-26 [claude]: Chose lock-file-presence + owner-agent-pid liveness over host-global pgrep: the existing PostToolUse release leg…
- 2026-06-26 [claude]: committed e30931c7 · 1 file
