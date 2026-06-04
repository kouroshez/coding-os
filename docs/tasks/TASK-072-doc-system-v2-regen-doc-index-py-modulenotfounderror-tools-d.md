---
id: TASK-072
title: "doc-system-v2: regen_doc_index.py ModuleNotFoundError(tools.docs) — make docs-index-regen + auto-regen hook silently broken"
swimlane: docs
kind: bug
epic: doc-system-v2
labels: [doc-index, regen, nav]
status: icebox
priority: P2
appetite: "1d"
created: 2026-06-04
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-072: doc-system-v2: regen_doc_index.py ModuleNotFoundError(tools.docs) — make docs-index-regen + auto-regen hook silently broken

**Outcome (one sentence):** make docs-index-regen and the auto-regen-doc-index hook invoke regen_doc_index.py under bare python3 without src/core/thinking_os on PYTHONPATH, so it dies with ModuleNotFoundError: tools.docs — every docs/<dir>/00-index.md silently stops regenerating. Fix the script's sys.path bootstrap so it self-resolves the package under bare python3 (works today only with PYTHONPATH=src/core/thinking_os).

## Read First
- docs/engineering/doc-system-overhaul-roadmap.md
- src/scripts/regen_doc_index.py
- src/core/hooks/auto-regen-doc-index.sh
- Makefile

## Repro Steps
1. (fill in: exact steps to reproduce)
2. ...
Expected: ...
Actual: ...

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** ...
- **When** ...
- **Then** ...

## Work Log
