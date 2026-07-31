---
id: TASK-652
title: "Reconcile astro problem.ts error shape (RFC 9457) with the canonical error envelope"
swimlane: templates
kind: chore
epic: stack-completeness-v2
labels: [astro, error-envelope, drift, ready]
status: archive
priority: P3
appetite: 1d
created: 2026-06-30
started: 2026-06-30
completed: 2026-06-30
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-652: Reconcile astro problem.ts error shape (RFC 9457) with the canonical error envelope

**Outcome (one sentence):** Decide whether astro's problem.ts (RFC 9457 application/problem+json) migrates to the canonical {error:{code,message,request_id}} envelope (as nestjs did in ea8efd8b) or is documented as an intentional per-stack exception; apply the decision to problem.ts, its sample test, and astro-rules.md.

## Work Log
- 2026-06-30 [claude]: problem.ts RFC9457->canonical {error:{code,message,request_id}} (like nestjs); 405 registered in error-format.md;…
- 2026-06-30 [claude]: committed 8ae1f46f · 12 files
