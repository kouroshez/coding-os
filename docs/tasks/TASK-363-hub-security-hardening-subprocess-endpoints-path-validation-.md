---
id: TASK-363
title: "Hub security hardening \u2014 subprocess endpoints, path validation, optional auth token"
swimlane: core
kind: security
epic: B-onboarding
labels: [wave-2, onboarding-program, ready]
status: complete
priority: P1
appetite: 1d
created: 2026-06-11
started: 2026-06-11
completed: 2026-06-11
agent_session: ses-claude-20260610-185418-2b3f
depends_on: [TASK-358]
blocked_by: []
references: []
---
# TASK-363: Hub security hardening — subprocess endpoints, path validation, optional auth token

**Outcome (one sentence):** /api/hub/registry/* and job endpoints validate paths against traversal, allowlist init arguments, optionally require a bearer token, and a short threat-model doc records the localhost-bind trust boundary.

## Read First
- src/core/web/routes/hub.py
- src/core/skills/security-web/SKILL.md
- docs/engineering/hub-architecture.md

## Threat Model
Attack surface: localhost-bound FastAPI that spawns `cos init` subprocesses and writes ~/.coding-os/registry.json. Actors: any local process/user able to reach 127.0.0.1:9188 (incl. malicious web pages attempting DNS-rebinding/CSRF against localhost). Assets: filesystem write via project_dir/name, command argv via template/agent/skills params, registry integrity. Out of scope: multi-user RBAC, network exposure (hub never binds non-loopback by default).

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a create/import request with `..`, symlinked, or absolute-escape paths, **When** any registry/job endpoint processes it, **Then** the request is rejected 400 with no filesystem effect (traversal regression tests for each endpoint).
- **Given** init parameters (template, agent, skills, preset), **When** the subprocess argv is built, **Then** every value is validated against the known registries (allowlist) — arbitrary strings never reach argv.
- **Given** COS_HUB_TOKEN set, **When** state-changing endpoints are called without the bearer token, **Then** 401; reads stay open; default (unset) keeps current open-localhost behavior; Origin/Host checked to block DNS-rebinding.
- **Given** the threat-model doc, **When** docs-lint runs, **Then** green and the doc cross-links hub-architecture.md.

## Work Log
- 2026-06-11 [claude]: DONE — COS_HUB_TOKEN bearer mode in SecurityGateMiddleware (401 on mutating /api without token, constant-time compare, f
