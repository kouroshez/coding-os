---
id: TASK-790
title: "fix(scheduled): session_summary.py as-file bootstrap omits src/ \u2014 silent ModuleNotFoundError every session-end"
swimlane: "thinking_os"
kind: bug
epic: null
labels: [ready]
status: complete
priority: P1
appetite: 1d
created: 2026-07-05
started: 2026-07-04
completed: 2026-07-04
agent_session: ses-claude-20260704-201536-1b8d
depends_on: []
blocked_by: []
references: []
---
# TASK-790: fix(scheduled): session_summary.py as-file bootstrap omits src/ — silent ModuleNotFoundError every session-end

**Outcome (one sentence):** session_summary.py self-bootstraps src/ onto sys.path (mirror nightly.py's _SRC/_CORE/_THINKING_OS trio) so its module-level `from core.logging_os import setup` resolves when run as a file by the session-end hook. A -S / env-scrubbed as-file smoke test folded into the test-thinking_os suite guards the regression (Rule 26 machine-check). The enriched session summary currently dies silently every session on any interpreter without the editable-install finder.

## Read First
- src/core/thinking_os/session_summary.py
- src/core/scheduled/nightly.py
- src/core/hooks/session-end.sh
- src/core/rules/test-discipline.md

## Repro Steps
On this machine: `python3 src/core/thinking_os/session_summary.py` → `ModuleNotFoundError: No module named 'core'` (line 66). session-end.sh line 76 invokes it via run_bounded_python → system python3 (no editable finder; `core resolvable: False`), stdout+stderr→DEVNULL, except:pass, hook exits 0 → the failure is invisible. Root: line 20 inserts only Path(__file__).parent (src/core/thinking_os); it needs parents[2] (src/) for top-level `core`.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the session-end hook runs session_summary.py as a file under an interpreter without the editable-install finder (system python3, or -S)
- **When** the test-thinking_os smoke test executes it as a subprocess
- **Then** the imports resolve and it exits 0 (no ModuleNotFoundError); with the bootstrap regressed the smoke test FAILS; verified by execution both directions.

## Work Log
- 2026-07-05 [claude]: Edit session_summary.py
- 2026-07-05 [claude]: Edit test_session.py
- 2026-07-05 [claude]: commit 90780f19e6 — fix(thinking_os): session_summary bootstraps src/ so it runs as a file
- 2026-07-05 [claude]: Fixed + committed (90780f19): session_summary bootstrap adds src/ (mirror nightly's _SRC/_HERE), + a -S as-file smoke…
