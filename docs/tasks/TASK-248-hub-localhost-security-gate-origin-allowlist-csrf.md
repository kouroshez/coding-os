---
id: TASK-248
title: "Hub localhost security gate (Origin allowlist + CSRF)"
swimlane: core
kind: security
epic: hub-redesign
labels: [ready]
status: complete
priority: P1
appetite: 1d
created: 2026-06-08
started: 2026-06-08
completed: 2026-06-08
agent_session: ses-claude-20260608-024900-f2b0
depends_on: []
blocked_by: []
references: []
---
# TASK-248: Hub localhost security gate (Origin allowlist + CSRF)

**Outcome (one sentence):** Reject cross-origin and DNS-rebinding requests and add CSRF protection on Hub mutation routes.

## Read First
- src/core/web/server.py — middleware registration point.
- src/core/web/routes/hub.py — the mutation routes (registry add/scan/gc) + _validate_project_path.
- docs/engineering/hub-architecture.md — the Hub contract.

## Context / Approach
Add an Origin/Host allowlist middleware (reject a non-localhost Origin → DNS-rebinding defense) plus a same-origin CSRF token on every state-changing route. The Hub binds 127.0.0.1 but is unauthenticated, so a drive-by page can POST to it once mutations exist. This GATES the new filesystem-write init route (TASK-249) — the single highest-severity new surface.

## Threat Model
- **Asset:** the Hub FastAPI server (binds 127.0.0.1:9188, unauthenticated) and its state-changing routes — project-registry mutations now, filesystem-scaffolding `init` (TASK-249) next.
- **Trust boundary:** the loopback interface. Anything that can make the user's browser issue a request to `127.0.0.1:9188` is in scope.
- **Threats (STRIDE):**
  - *DNS rebinding (Spoofing / EoP):* a malicious page rebinds its hostname to 127.0.0.1 and scripts requests at the Hub. **Mitigation:** Host/Origin allowlist — accept only `localhost`/`127.0.0.1`/`[::1]` (+ configured port); reject everything else with 403.
  - *CSRF (Tampering):* a drive-by page POSTs to a mutation route via the user's browser. **Mitigation:** a same-origin double-submit CSRF token required on every state-changing method (POST/PUT/PATCH/DELETE).
  - *Cross-origin read (Information disclosure):* constrained by the existing CORS allowlist; verify GETs are not opened by a permissive CORS during this change.
- **Out of scope:** a network attacker (loopback-only bind), multi-user authz (single local user), and the SDK chat-session sandbox (TASK-246).
- **Residual risk:** a local malicious *process* able to read the token from the page — acceptable for a single-user local tool; documented, not mitigated here.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a non-localhost Origin on a mutation route, **When** received, **Then** it is rejected (403).
- **Given** a same-origin request, **When** received, **Then** it passes.

## Work Log
- 2026-06-08 [claude]: Added SecurityGateMiddleware (Origin/Host allowlist + CSRF double-submit), SPA CSRF header, doc section; 57 web tests gr
