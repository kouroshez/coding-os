---
id: TASK-1059
title: "Fix the third review: Hub bind guard on the real host, Astro lexer gaps, include normalisation"
swimlane: "graph_os"
kind: bug
epic: null
labels: [docs-update, ready]
status: complete
priority: P2
appetite: 1d
created: 2026-10-09
started: 2026-10-08
completed: 2026-10-08
agent_session: ses-claude-20261004-231430-d18a
depends_on: []
blocked_by: []
references: []
---
# TASK-1059: Fix the third review: Hub bind guard on the real host, Astro lexer gaps, include normalisation

**Outcome (one sentence):** The Hub refuses an off-loopback bind by the host it actually binds, and every confirmed finding of the third review (Astro template literals and void tags, prose annotations, include globs, the fragment test, the post-link warning, RISK-004 wording) is fixed with a test.

## Read First
- src/core/web/server.py
- src/core/web/security.py
- src/core/graph_os/extractors/_astro_template.py
- docs/governance/risk-register.md

## Repro Steps
1. Unset `COS_HUB_TOKEN` and `COS_WEB_HOST`, then run `cos board --web --bind 0.0.0.0`.
2. `run_server` passes the host only to uvicorn; `create_app` guards `COS_WEB_HOST`, which still reads loopback.
Expected: the Hub refuses to start.
Actual: it binds every interface with no token. The other findings are listed in docs/engineering/graph-os-polyglot-audit-2026-10-07-final-round.md § Third review.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** `cos board --web --bind 0.0.0.0` with no token
- **When** the Hub starts
- **Then** it refuses before the port opens, and each other finding has a test that fails on the old code

## Work Log
- 2026-10-09 [claude]: commit cfa6ab8e1d — fix(web): refuse an off-loopback Hub bind by the host run_server binds, not only COS_WEB_HOST
- 2026-10-09 [claude]: Status transitioned to complete via cos task-done.
