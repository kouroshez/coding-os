---
id: TASK-1141
title: "fix(install): META install.sh localizes links through the same step cos update uses (audit L3)"
swimlane: infra
kind: bug
epic: null
labels: [ready]
status: icebox
priority: P2
appetite: 1d
created: 2026-11-26
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-1141: fix(install): META install.sh localizes links through the same step cos update uses (audit L3)

**Outcome (one sentence):** META's .claude/ links are written by one install path, the same localize step cos update runs, so META links are relative as the localize contract says (audit L3).

## Read First
- docs/engineering/harness-loading-audit-2026-11.md
- docs/engineering/rules-loading.md

## Repro Steps
1. In coding-os, run `bash src/adapters/claude/install.sh`.
2. Run `find .claude -type l -lname '/*' | wc -l`.
Expected: 0 (the localize contract in `_localize_links.py` says META links are relative).
Actual: about 290 absolute links, written by `install-adapter.sh`.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** META after bash src/adapters/claude/install.sh, **When** find .claude -type l -lname '/*' runs, **Then** it prints nothing.
- **Given** a consumer that still carries localized .codex/rules/*.md copies from before TASK-1135, **When** cos update runs, **Then** the managed copies are removed and any user-owned *.rules file stays.

## Work Log
