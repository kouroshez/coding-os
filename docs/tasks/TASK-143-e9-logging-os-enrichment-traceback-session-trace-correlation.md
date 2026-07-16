---
id: TASK-143
title: "E9: logging_os enrichment — traceback + session/trace correlation + PII redaction + fatal worker-safe + error(exc=)"
swimlane: infra
kind: feature
epic: observability-eye
labels: [observability, logging_os, redaction, ready]
status: archive
priority: P1
appetite: "1d"
created: 2026-06-05
started: 2026-06-05
completed: 2026-06-05
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-143: E9: logging_os enrichment — traceback + session/trace correlation + PII redaction + fatal worker-safe + error(exc=)

**Outcome (one sentence):** Durable errors become actionable + safe: error()/fatal() accept exc= and capture a truncated stack; the stdlib bridge records the traceback (not just the class name); _emit stamps session_id/trace_id from env so a row joins the cognition trace; a redaction pass scrubs secret shapes before any sink; fatal() raises CosFatalError instead of sys.exit(1) so it cannot kill a server/MCP worker.

## Read First
- docs/engineering/observability-eye.md
- src/core/logging_os/api.py
- src/core/logging_os/bridge.py
- src/core/logging_os/config.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** an exception e, COS_SESSION_ID set, and a message containing `token=abc123secretvalue`
- **When** logging_os.error("a.b", "msg token=abc123secretvalue", exc=e) is emitted
- **Then** the event carries kv.exc=type(e).__name__, a non-empty event.stack, session_id from env, and the secret is replaced with <redacted> before any sink; fatal() raises CosFatalError (not SystemExit); the bridge records a stack on exc_info; and the logging_os suite (incl new tests) is green

## Work Log
- 2026-06-05 [claude]: logging_os enrichment: new redact.py (secret-shape + sensitive-key scrub before all sinks); config.session_id()/trace_id
