---
id: TASK-1035
title: "Split pr_commands.py and embeddings.py along their real seams, then delete their ledger entries"
swimlane: cli
kind: refactor
epic: null
labels: [parked]
status: icebox
priority: P3
appetite: 1d
created: 2026-09-14
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-1035: Split pr_commands.py and embeddings.py along their real seams, then delete their ledger entries

**Outcome (one sentence):** `pr_commands.py` and `embeddings.py` are split into modules that each own one responsibility, and their entries leave `file-size-baseline.json` — the only way the ratchet is allowed to tighten.

## Read First
- docs/engineering/ci-gates.md § File-size ratchet · § Split parity
- file-size-baseline.json
- src/cli/pr_commands.py · src/core/thinking_os/embeddings.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** the split has landed
**When** `check_split_parity.py` compares the pre-split ref to the new package
**Then** it reports no vanished function and no changed body — the refactor
carried no ride-along edit.

**Given** the two files are under 500 lines
**When** `file-size-baseline.json` is read
**Then** only `_db_migrations.py` remains, because the ratchet tightens by
deleting entries and never by raising a number.

**Given** the pr-mode suites
**When** they run after the split
**Then** they pass with every `monkeypatch.setattr` retargeted at the module
that owns the name — not passing because a patch quietly became a no-op.

## Work Log
