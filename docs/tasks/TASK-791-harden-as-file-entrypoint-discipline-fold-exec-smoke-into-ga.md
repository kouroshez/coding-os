---
id: TASK-791
title: "harden as-file entrypoint discipline: fold exec-smoke into gated suites, normalize bootstraps, surface swallowed hook failures"
swimlane: core
kind: chore
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
# TASK-791: harden as-file entrypoint discipline: fold exec-smoke into gated suites, normalize bootstraps, surface swallowed hook failures

**Outcome (one sentence):** The structural follow-ups from the nightly-drift audit (workflow wf_d469d339) that make Rule 26 enforceable rather than convention-only, each the smallest correct change: (1) normalize responsive_extract.py's bootstrap to the src/-inclusive shape [_SRC,_CORE,_THINKING_OS] — inline, no shared helper (Rule-of-Three not met); (2) run_bounded_python (session-end.sh) emits ONE cos_log_hook breadcrumb on non-zero child rc only, keeping stderr→DEVNULL otherwise, so a broken as-file script is visible in `cos hooks-log`; (3) one invariant sentence in docs/engineering/scheduled-jobs.md + hook-authoring: a hook-invoked as-file script must self-bootstrap src/ (the editable install is absent in delivered/consumer environments); (4) add a 'Smoke / run-the-deliverable' row to testing-strategy SKILL.md AND references/test-types.md (ssot — both or neither); (5) wire one orphaned smoke_*.py into make/CI or delete the set (defer-by-default).

## Work Log
- 2026-07-06 [claude]: Edit responsive_extract.py
- 2026-07-06 [claude]: Edit session-end.sh
- 2026-07-06 [claude]: Edit scheduled-jobs.md
- 2026-07-06 [claude]: Edit SKILL.md
- 2026-07-06 [claude]: Edit SKILL.md
- 2026-07-06 [claude]: Edit test-types.md
- 2026-07-06 [claude]: Edit Makefile
- 2026-07-06 [claude]: commit e1090cb603 — chore(scheduled): harden as-file entrypoint discipline for Rule 26 enforceability
- 2026-07-06 [claude]: All 5 items shipped. (1) responsive_extract.py bootstrap now [_SRC,_CORE,_THINKING_OS] (src/ first) so `from…
