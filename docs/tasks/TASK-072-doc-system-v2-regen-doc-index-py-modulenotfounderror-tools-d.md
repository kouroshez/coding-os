---
id: TASK-072
title: "doc-system-v2: regen_doc_index.py ModuleNotFoundError(tools.docs) — make docs-index-regen + auto-regen hook silently broken"
swimlane: docs
kind: bug
epic: doc-system-v2
labels: [doc-index, regen, nav]
status: complete
priority: P2
appetite: "1d"
created: 2026-06-04
started: 2026-06-03
completed: 2026-06-04
agent_session: ses-claude-20260527-151803-0b9f
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
1. From repo root run `make docs-index-regen` (or bare `python3 src/scripts/regen_doc_index.py docs --all`).
Expected: every `docs/<dir>/00-index.md` regenerated from frontmatter, exit 0.
Actual: `ModuleNotFoundError: No module named 'tools'` at import (line 17), exit 1, no index written. Only `PYTHONPATH=src/core/thinking_os` makes it run.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** `regen_doc_index.py:12-13` computes `_THINKING_OS = _REPO_ROOT / "core" / "thinking_os"` where `_REPO_ROOT` is the repo root (3× `.parent`), so the path is missing the `src/` segment and `from tools.docs import …` fails under bare `python3`.
- **When** the sys.path bootstrap is corrected to resolve `src/core/thinking_os`.
- **Then** `make docs-index-regen` and bare `python3 src/scripts/regen_doc_index.py <dir>` exit 0 and regenerate every `docs/<dir>/00-index.md` with no PYTHONPATH, so the auto-regen-doc-index hook stops failing silently; `make docs-lint` stays EXIT 0. (Docs lacking canonical frontmatter — e.g. logging_os.md, doctor-checks.md — remain correctly skipped; adding their frontmatter is a separate G3 enforcement concern, not this import bug.)

## Work Log
- 2026-06-04 [claude]: Status transitioned to complete via cos task-done.
