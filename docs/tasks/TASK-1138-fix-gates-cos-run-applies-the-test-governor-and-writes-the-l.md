---
id: TASK-1138
title: "fix(gates): cos run applies the test governor and writes the ledger; blocking hooks fail closed without cos"
swimlane: infra
kind: bug
epic: null
labels: [ready]
status: complete
priority: P1
appetite: 2d
created: 2026-11-26
started: 2026-11-26
completed: 2026-11-26
agent_session: ses-claude-20261126-141006-6f9e
depends_on: []
blocked_by: []
references: []
---
# TASK-1138: fix(gates): cos run applies the test governor and writes the ledger; blocking hooks fail closed without cos

**Outcome (one sentence):** Tests run through cos run are deduped, locked and ledgered by cos run itself, consumer suites match the stack layout, and enforcement does not silently vanish; findings G2, G3 and G4 of the [audit § Gates](../engineering/harness-loading-audit-2026-11.md#gates) are closed.

## Read First
- docs/engineering/harness-loading-audit-2026-11.md
- docs/engineering/test-governance.md

## Repro Steps
In a fastapi scaffold `cos run test-backend` passes test-governor.sh untouched (fast path needs pytest or make, :28-31) while record-verify-auto ledgers it (audit G2).

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a green ledger entry for test-backend on the same tree, **When** `cos run test-backend` runs again, **Then** it is refused unless forced.
- **Given** `cos run test-backend` exits non-zero, **When** it returns, **Then** cos run itself has written FAIL for test-backend to .last-verify.json, with no hook involved.
- **Given** a fastapi scaffold with a change under src/backend/, **When** the required suites are matched, **Then** test-backend is required.
- **Given** a scaffold with cos off PATH, **When** a blocking hook fires, **Then** it blocks with an install hint, and an observer hook exits 0.
- **Given** the built wheel, **When** its contents are listed, **Then** core/hooks/_helpers/*.sh is present.

## Work Log
- 2026-11-26 [claude]: Plan (graph+rg consumers): (1) verify_suites_cli: extract match_command() from cmd_match_command (only caller: main…
- 2026-11-26 [claude]: Plan (graph+rg consumers): (1) verify_suites_cli: extract match_command() from cmd_match_command (only caller: main;…
- 2026-11-26 [claude]: Implemented: cli/_run_gate.py (sweep/dedup/lock + record-verify.sh ledger) wired into cos run;…
- 2026-11-26 [claude]: Clean clone (HEAD 3b9b4f29 + this diff only): golden-capture rewrote 730 golden hook files, every one byte-equal to…
- 2026-11-26 [claude]: commit c679e5b705 — fix(gates): shim fails closed only for default-blocking hooks and honours the bootstrap escape
- 2026-11-26 [claude]: Review round 1 → c679e5b7. Fixed: (M1) shim honours COS_ALLOW_MISSING_DEPS=1 (the existing cos_require_parser escape)…
- 2026-11-26 [claude]: commit 93e3aa7944 — fix(gates): codex dispatchers fail closed without cos; cos run owns its lock atomically
- 2026-11-26 [claude]: Review round 2 → 93e3aa79. Fixed: (S1 medium) shim list adds codex-pretool/preedit/stop/postedit-dispatch (the…
- 2026-11-26 [claude]: commit 4c03f2ea03 — fix(gates): cos run tries the exclusive lock create first and replaces only a stale holder
- 2026-11-26 [claude]: Round 3: reviewer and security auditor both passed. Fixed the shared low anyway (4c03f2ea): _take_lock tries…
- 2026-11-26 [claude]: Round 4 reviewer passed. Accepted lows, not fixed: (1) an O_EXCL-created lock not yet written reads as unreadable and…
- 2026-11-26 [claude]: Status transitioned to complete via cos task-done.
