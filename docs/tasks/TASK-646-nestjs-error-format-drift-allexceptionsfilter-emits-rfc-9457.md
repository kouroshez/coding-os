---
id: TASK-646
title: "nestjs error-format drift \u2014 AllExceptionsFilter emits RFC 9457, contradicting the shipped error-format.md SSOT"
swimlane: templates
kind: bug
epic: stack-completeness-v2
labels: [nestjs, drift, wave-1, api-contract, ready]
status: archive
priority: P2
appetite: 1d
created: 2026-06-30
started: 2026-06-30
completed: 2026-06-30
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-646: nestjs error-format drift — AllExceptionsFilter emits RFC 9457, contradicting the shipped error-format.md SSOT

**Outcome (one sentence):** The shipped nestjs AllExceptionsFilter emits the canonical envelope from docs/api-contracts/error-format.md ({error:{code,message,request_id}}) instead of the contradictory RFC 9457 {type,title,status}, so a consumer following the shipped SSOT doc and the shipped filter get the same wire shape.

## Read First
- src/templates/_base/scaffold/docs/api-contracts/error-format.md
- src/templates/nestjs/scaffold/src/backend/src/common/all-exceptions.filter.ts

## Repro Steps
1. Open src/templates/nestjs/scaffold/src/backend/src/common/all-exceptions.filter.ts — it responds application/problem+json with {type,title,status} (RFC 9457).
2. Open the SSOT it ships beside: src/templates/_base/scaffold/docs/api-contracts/error-format.md — mandates {error:{code,message,details,request_id}}.
Expected: filter output matches the SSOT envelope.
Actual: a consumer frontend coded to error-format.md reads response.error.code → undefined; two incompatible contracts ship in one project.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the rewritten filter, **When** an HttpException such as 404 is thrown, **Then** the response is application/json `{error:{code:"NOT_FOUND", message, request_id}}`.
- **Given** a non-HttpException, **When** it is caught, **Then** status is 500 with code `INTERNAL_ERROR` and a generic message (no internal detail leaked).
- **Given** the template suite, **When** `uv run pytest tests/test_template_scaffold.py -q` runs, **Then** green; and `uv run cos stack-lint nestjs` PASS.

## Work Log
- 2026-06-30 [claude]: Edit all-exceptions.filter.ts
- 2026-06-30 [claude]: Edit SKILL.md
- 2026-06-30 [claude]: Edit nestjs-service.md
- 2026-06-30 [claude]: filter→{error:{code,message,request_id}} json; SKILL+playbook drop RFC9457/problem wording. stack-lint nestjs PASS;…
