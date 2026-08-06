---
id: TASK-804
title: "Owner-gated legacy changelog sweep tool (cos brain-sweep-changelog: dry-run default, archive-first --confirm, --undo, --vacuum)"
swimlane: cli
kind: feature
epic: null
labels: [ready]
status: archive
priority: P2
appetite: 1d
created: 2026-07-05
started: 2026-07-06
completed: 2026-07-06
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-804: Owner-gated legacy changelog sweep tool (cos brain-sweep-changelog: dry-run default, archive-first --confirm, --undo, --vacuum)

**Outcome (one sentence):** The owner can retire the ~4566 legacy mechanical `changelog` rows (NULL expiry, pre-dating the TTL wiring) via an archive-first, dry-run-default CLI they invoke deliberately — never auto-run.

## Read First
- src/core/thinking_os/memory_gc.py (add `sweep_changelog` / undo / vacuum next to the existing gc, argparse)
- src/cli/brain_commands.py (+ `brain-sweep-changelog` wrapper) · src/cli/main.py (command registration)
- TASK-803 (forward TTL wiring — done): new rows already expire; this sweeps the legacy backlog only.

## Scope (the owner-gated BACKFILL half of F — deliberately NOT auto-run)
- `sweep_changelog` in memory_gc.py, surfaced as `cos brain-sweep-changelog`: **default dry-run** (report matched count); `--confirm` archives-first to gzip JSONL under `.coding-os/archives/` then reclassifies/deletes; `--undo` restores from the archive; `--vacuum` reclaims file bytes (exclusive lock — quiescence only).
- Predicate matches ONLY legacy rows: `memory_type='changelog' AND expires_at IS NULL`, EXCLUDING tool_failure/completion_gap (mining fuel). This is disjoint from decay's forward GC (which only touches `expires_at IS NOT NULL`).
- NOT a migration (a migration would auto-run unattended against every consumer DB — this must stay owner-invoked).

## Owner sign-off required before running --confirm
Do NOT run `--confirm` against the live meta-repo DB as part of this task — ship the tool; the owner invokes it. `--grace-days` < 14 and `--vacuum` (rewrites ~600MB) need explicit owner go-ahead.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a corpus of legacy changelog rows (NULL expiry) plus some tool_failure rows,
- **When** `cos brain-sweep-changelog` runs dry (default),
- **Then** it reports the matched legacy count excluding tool_failure and writes nothing; `--confirm` archives-then-removes and `--undo` restores byte-for-byte; the CLI smoke-runs (`--help`), test_cli covers the wrapper, and the thinking_os matrix stays green.

## Dependencies
- TASK-803 (forward TTL wiring) — done.

## Work Log
- 2026-07-06 [claude]: Edit memory_gc.py
- 2026-07-06 [claude]: Edit memory_gc.py
- 2026-07-06 [claude]: Edit brain_commands.py
- 2026-07-06 [claude]: Edit main.py
- 2026-07-06 [claude]: Edit main.py
- 2026-07-06 [claude]: Edit test_brain_hardening.py
- 2026-07-06 [claude]: Edit test_cli.py
- 2026-07-06 [claude]: Edit test_cli.py
- 2026-07-06 [claude]: commit 274698117e — feat(cli): add owner-gated brain-sweep-changelog to retire legacy changelog rows
- 2026-07-06 [claude]: Built sweep_changelog/undo_sweep/vacuum_db in memory_gc.py + brain-sweep-changelog CLI (dry-run default; --confirm…
