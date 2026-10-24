<!-- domain:BACKEND | layer:reference | ssot:true | updated:2026-06-04 -->
# Backend Patterns — Layering, Idempotency, Errors, Scale

> P: The stack-agnostic backend patterns that keep a service testable and correct under load.
> R: Writing or reviewing any server-side code (handler, service, query, job, webhook).
> S: Stack-specific framework idioms — that's your stack skill (python-fastapi/go-fiber/…).
> N: [SKILL.md](../SKILL.md), [backend-checklist.md](../assets/backend-checklist.md)

> Nav: [Skill](../SKILL.md)

## Layering — thin delivery, fat core, framework-free domain

```
handler (HTTP/framework)  →  service (business rules)  →  repository (data)
   parse + validate            the actual logic            the only SQL/ORM
```

The handler translates HTTP to a plain call and back; the service holds the rules
and knows nothing about HTTP; the repository is the only place with SQL/ORM. A
service that imports Flask/Express or touches `request`/`response` has coupled the
core to delivery — `check_layering.py` flags it. The deep treatment is the
hexagonal-architecture skill.

## Idempotency — safe to retry

Networks retry. A `POST /charge` that runs twice double-charges. Make
state-changing operations idempotent: an idempotency key the server dedupes on, or
an upsert keyed by a natural id. Webhooks especially — providers retry on any
non-2xx, so handlers must tolerate duplicates.

## Error envelope — one shape, everywhere

Return errors in one consistent shape (`{error: {code, message}}` / the repo's
`ok`/`fail`), with the right status code. Never leak stack traces or internal
detail to the client; log the detail server-side with a correlation id. The
contract discipline is owned by api-contract-discipline (a co-shipping rule) and
[api-design](../../api-design/SKILL.md).

## N+1 and scale-aware data access

The most common real slowness is N+1 (a query per row) — batch or join
([sql-authoring](../../sql-authoring/SKILL.md)). Paginate every list endpoint
(keyset at scale). Assume the table grows: an `ORDER BY` with no index, a full
scan, or an unbounded result that's fine at 1k rows melts at 10M.

## Background work off the request path

Anything slow or retryable (email, image processing, third-party calls) goes to a
queue/worker, not the request thread — the user gets a fast response, the work
retries on failure. Keep the request handler doing request-shaped work only.

## Migrations — backward-compatible, expand→contract

A migration must work with the currently-running code (both versions run during a
rolling deploy). Add then later remove; never drop a column the live code still
reads. ([deployment-cicd](../../deployment-cicd/SKILL.md) covers the deploy ordering.)
