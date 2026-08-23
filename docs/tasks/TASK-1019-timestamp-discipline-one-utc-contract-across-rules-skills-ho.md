---
id: TASK-1019
title: "Timestamp discipline \u2014 one UTC contract across rules, skills, hooks and helpers"
swimlane: core
kind: chore
epic: null
labels: [governance, docs-update, ready]
status: complete
priority: P1
appetite: 1d
created: 2026-08-23
started: 2026-08-23
completed: 2026-08-23
agent_session: ses-claude-20260823-134429-13ad
depends_on: []
blocked_by: []
references: []
---
# TASK-1019: Timestamp discipline — one UTC contract across rules, skills, hooks and helpers

**Outcome (one sentence):** Every timestamp the kernel writes or reads uses one documented representation, and the agent-facing instruction layer (rule + skill + write-time hook + CI test) makes the wrong choice unavailable rather than merely discouraged.

## Work Log
- 2026-08-23 [claude]: Audit found four live timestamp shapes in src/: strftime ISO-Z, isoformat(+00:00), isoformat(micro), and SQLite…
- 2026-08-23 [claude]: Chose to document the legacy column spread rather than migrate it, and to warn rather than block at write time —…
- 2026-08-23 [claude]: commit aea0664cb1 — docs(governance): add Rule 28 — one timestamp contract, UTC at rest
- 2026-08-23 [claude]: commit 07eee22488 — fix(core): collapse six now_iso variants onto one UTC form and drop naive stamps
- 2026-08-23 [claude]: commit a5e643bcb4 — feat(hooks): warn at write time on timestamp forms that store the wrong instant
- 2026-08-23 [claude]: commit 21586deab0 — fix(tests): exempt the canonical format definition from the now_iso gate
- 2026-08-23 [claude]: commit f0b068128a — chore(regen): add the timestamp rule to every golden scaffold
- 2026-08-23 [claude]: Verified by executing: negative-tested the CI gate by injecting a drifted producer and a utcnow() into a tracked file…
- 2026-08-23 [claude]: Status transitioned to complete via cos task-done.
