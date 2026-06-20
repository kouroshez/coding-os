---
id: TASK-487
title: "Gate Hub read routes behind COS_HUB_TOKEN when bound to a non-loopback host"
swimlane: core
kind: security
epic: null
labels: [hub, deferred, ready]
status: complete
priority: P3
appetite: 1d
created: 2026-06-20
started: 2026-06-20
completed: 2026-06-20
agent_session: ses-claude-20260620-144553-a8b6
depends_on: []
blocked_by: []
references: []
---
# TASK-487: Gate Hub read routes behind COS_HUB_TOKEN when bound to a non-loopback host

**Outcome (one sentence):** When the Hub is configured to bind to a non-loopback host (reverse-proxy / shared dev box), read routes — not just mutations — require the COS_HUB_TOKEN bearer, so a remotely reachable Hub does not serve the entire proprietary code graph unauthenticated. Deferred until remote/hosted Hub is an actual launch decision; loopback default stays token-free.

## Read First
- src/core/web/security.py
- src/core/web/_envelope.py
- docs/engineering/hub-threat-model.md
- src/core/web/ui/src/

## Threat Model
- **Attacker:** anyone with network reach to a Hub that has been bound to a non-loopback address (reverse-proxy, shared cloud dev box / Coder / Gitpod, or a mis-configured 0.0.0.0 bind) — a LAN peer, another tenant on the shared host, or an internet scanner if exposed.
- **Asset:** the entire proprietary code knowledge graph of every project the Hub serves (symbols, file paths, signatures, docstrings, architecture map) plus read access to memory/docs/tasks via `/api/*` — effectively a full structural blueprint of the codebase.
- **Attack vector:** read `GET /api/*` routes currently bypass SecurityGateMiddleware (it checks only `_MUTATING_METHODS`, security.py:88-96), so the moment the Hub leaves loopback an unauthenticated request can enumerate the whole graph.
- **Mitigation:** when `COS_HUB_TOKEN` is set AND the bind host is non-loopback, require the bearer on reads too (401 otherwise); keep the loopback `127.0.0.1` default token-free so local single-user dev is unchanged. Non-loopback is detected by comparing the resolved request host against `_BASE_ALLOWED_HOSTS` (security.py:28 — {localhost, 127.0.0.1, ::1}); any host outside that set is treated as remote. Record the boundary in hub-threat-model.md. (Full RBAC/SSO/tenancy stays explicitly out of scope — it would replace this token wholesale.)

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** SecurityGateMiddleware currently gates only _MUTATING_METHODS (security.py:88-96) and has zero bind-host awareness, while read /api/* paths are unauthenticated, **When** COS_HUB_TOKEN is set AND the bind host is non-loopback, **Then** read /api/* paths also require the bearer and return 401 on missing/invalid token. **And** non-loopback is detected via the resolved request host NOT being in the loopback set `_BASE_ALLOWED_HOSTS` (security.py:28 — {localhost, 127.0.0.1, ::1}), with the X-Forwarded-For / reverse-proxy host-spoofing caveat documented in hub-threat-model.md. **And** 401 is added to ENVELOPE_ERROR_RESPONSES (_envelope.py). **And** the SPA api-client attaches the bearer on read requests. **And** hub-threat-model.md and hub-architecture.md record the non-loopback read-auth boundary. **And** the loopback 127.0.0.1 default behaviour is byte-unchanged (no token required).

## Work Log
- 2026-06-20 [claude]: Server-side read-auth shipped: SecurityGateMiddleware now requires the COS_HUB_TOKEN bearer on read GET /api/* when…
- 2026-06-20 [claude]: committed 40d5f4ca · 5 files
