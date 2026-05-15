---
name: backend-fundamentals
description: Stack-agnostic backend patterns. Use when writing or modifying any server-side code (HTTP handler, DB query, background job, auth/middleware, webhook) regardless of language or framework. Covers services/selectors split, idempotency, error envelopes, migration discipline, N+1 avoidance, scale-aware design, auth guardrails, and logging hygiene.
globs: "backend/**/*"
paths: ["backend/**/*"]
context: fork
depends_on:
  - clean-code
allowed-tools:
  - Read
  - Grep
  - Glob
  - Edit
  - Write
last_reviewed: "2026-05-11"

---

# Backend Fundamentals — Stack-Agnostic Patterns

Universal guidance that holds for Django, FastAPI, Go (stdlib + Fiber), Rails, NestJS, Spring, and any other server-side framework. Framework-specific layering (DRF ViewSets, Pydantic `Depends`, Fiber middleware chain) lives in the stack-specific skill that `depends_on: [backend-fundamentals]`.

Loaded automatically when `enforce-skill.sh` routes a file under `backend/` that matches a stack skill.

## 0. Scale mindset (think before writing)

Every handler, query, and API must be written as if it will be called by 1,000 concurrent users on a 50M-row table. Before writing:

- **How many rows does this touch?** Unknown → run `EXPLAIN ANALYZE` or ask.
- **How many callers at once?** Single-user admin page vs. public endpoint changes everything.
- **Where's the bottleneck?** DB index miss · network hop · CPU work.
- **What's the latency budget?** Default P99 < 500 ms; surface the number in the PR description.
- **What happens if step 3 of 5 fails?** Transactions · idempotency key · compensating action.

Code that works on 10 rows but collapses on 10 M is a production incident waiting for traffic. Correct answer to "will this scale?" is a number, not "yes".

## 1. Service / selector split

Business logic lives in **services** (write path — mutates state, encapsulates a transaction). Read-only DB queries live in **selectors** (pure functions, cached when possible). Controllers / views / handlers only:

1. Parse and validate the request.
2. Call a service or selector.
3. Shape the response.

No ORM calls in controllers. No business rules in serializers. No DB writes in selectors. This split makes unit testing trivial (mock the service boundary) and keeps transaction boundaries visible.

## 2. Standard response envelope

Every handler returns **one** of:

```json
{ "ok": true,  "data":  <T> }
{ "ok": false, "error": { "code": "<UPPER_SNAKE>", "message": "<human>", "retryable": true|false } }
```

Error codes come from a **project-level registry** (list every code in one file, e.g. `backend/errors.py` or `docs/api-contracts/error-codes.md`). Never invent codes on the fly — if a new case doesn't fit an existing code, add the new code to the registry first, then reference it.

`retryable` tells the client whether retry helps: transient/infrastructure errors `true`, validation/permission/not_found `false`. Prevents infinite retry loops on deterministic failures.

## 3. Idempotency — every state-changing call

Every endpoint that mutates state MUST accept (or derive) an idempotency key:

- Webhook → key = `<provider>:<event_id>` (Stripe, Square, GitHub, ...).
- Internal service call → key = `sha256(normalized_input_json)`.
- User-initiated → key = `Idempotency-Key` header (RFC 8594-style).

Persist the key **before** side effects. Three states: `processing`, `processed`, `failed`. If the key already exists as `processing`/`processed`, return the stored response — do NOT re-apply the operation. Multi-table writes MUST run inside a single transaction; on rollback, also roll back the idempotency row.

Without this discipline: double-charge, duplicate fulfillment, duplicate email sends. It's the single most common production bug on payment / webhook paths.

## 4. N+1 query prevention

If you see a `for` loop with a DB call inside, it's wrong:

```python
# WRONG — 1 query + N queries
for order in orders:
    order.customer = db.get_customer(order.customer_id)

# RIGHT — 2 queries total
customer_ids = {o.customer_id for o in orders}
customers = db.get_customers_by_ids(customer_ids)
customer_by_id = {c.id: c for c in customers}
for order in orders:
    order.customer = customer_by_id[order.customer_id]

# OR use ORM join/prefetch:
orders = Order.objects.select_related("customer")  # Django
orders = db.query(Order).options(joinedload(Order.customer))  # SQLAlchemy
```

Rule: before a loop over DB rows, materialize the join batch. ORMs have `select_related` / `prefetch_related` / `joinedload` / `Preload` — learn the one for your stack.

## 5. Indexes on every WHERE / JOIN / ORDER BY

If a column appears in `WHERE`, `JOIN`, or `ORDER BY` on a table expected to have > 10K rows, it MUST have an index. Verify with `EXPLAIN ANALYZE` on the real DB (not a fresh dev DB with 10 rows — fake stats lie).

For composite predicates, the index column order matters: most-selective-first for equality, then range. E.g., `WHERE user_id = ? AND created_at > ?` wants `(user_id, created_at)`, not `(created_at, user_id)`.

No "full table scan" on production-sized tables is acceptable. Index maintenance cost ≪ scan cost once data grows.

## 6. Pagination — never return all rows

Offset pagination is fine for small admin lists (LIMIT + OFFSET up to page 50). **Cursor-based pagination is required** when:

- Result set > 10K rows, or
- Deep pages are common (page 500+), or
- Inserts happen concurrently (offset drifts).

Cursor = opaque token encoding the last-seen sort key (e.g., base64-encoded `(created_at, id)` tuple). Return `next_cursor` in the response envelope; client echoes it back as `cursor=` in the next call.

Hard cap: MAX 100 rows per page. Client-supplied `limit` > 100 is rejected as `VALIDATION_ERROR`.

## 7. Transactions — atomicity for multi-step writes

Any operation that writes to ≥ 2 tables (or inserts to 1 and updates another) MUST run inside one transaction:

```python
with db.transaction():
    idempotency_row = create_idempotency_row(key, status="processing")
    order = create_order(payload)
    inventory_reserve(order.items)
    # If any step raises, ALL rollback — no partial state.
    idempotency_row.status = "processed"
```

Transactions should be **short**. Never hold an open transaction while calling an external API (Stripe, email provider, S3). Pattern: (1) short DB tx to stage, (2) release connection, (3) external call, (4) short DB tx to commit. Long-held transactions exhaust connection pools under load.

## 8. Migrations — append-only, forward-safe

- **Append-only.** New tables / columns → new migration. Never edit a past migration that's been deployed.
- **Forward-safe.** Every migration must be applicable to a database where previous migrations ran. Destructive changes (drop column, rename) need a two-step dance: deploy code that doesn't use the column → migration drops it → deploy next release.
- **Idempotent.** `CREATE TABLE IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`, `INSERT ... ON CONFLICT DO NOTHING`. Re-applying a migration on the same DB must be safe.
- **Reversible when practical.** Every migration file has a `down` / `revert` section. Data migrations are the exception — document why revert is manual.
- **No secrets in migrations.** API keys, JWTs, service-role credentials go via vault / dashboard / env. Document the manual step as a comment in the closest related migration.

## 9. Auth / permissions — default deny

- **Default deny.** No endpoint is public unless explicitly marked. Framework defaults (Django's `IsAuthenticated`, FastAPI's `Depends(get_current_user)`, Fiber's auth middleware) go at the router/app level, exemptions are the ones with decorators.
- **Identity vs. authorization.** "Who is this request?" is authentication (JWT / session). "Can they do X to Y?" is authorization (RBAC / row-level). Keep them in separate layers — a service method receives `user_id` and re-checks permissions, doesn't trust the controller.
- **Row-level security.** For multi-tenant data, every query that touches a tenant-scoped table MUST filter by tenant_id in WHERE. The DB layer (RLS in Postgres, filter in ORM manager) is the last line, not the only line.
- **Re-verify before destructive ops.** Email-change, password-reset, account-delete: require recent re-auth (timestamp on the session < 5 min old) regardless of existing login.

## 10. Logging — step-numbered, redacted, correlatable

```python
log.info("🟣 STEP 1 — validating input", extra={"trace_id": trace_id, "user_id": user_id})
log.info("✅ STEP 1 OK — 3 items")
log.info("🟣 STEP 2 — charging gateway")
log.info("🔥 FATAL — gateway error %s", err_code, extra={"trace_id": trace_id})
```

- Every log line carries `trace_id` (from request header or generated) so a support ticket can be traced end-to-end.
- **Redact PII and secrets.** Allow-list of fields to log; everything else masked. Never log raw request/response JSON on payment or auth paths.
- Emoji step markers (🟣 start, ✅ ok, ⚠️ warn, 🔥 fatal) make grep easier and reduce the temptation to write `print("got here")` debug code.

## 11. External calls — timeouts, retries, circuit breakers

Any call to a system you don't control (payment gateway, email provider, S3, third-party API):

- **Timeouts.** Hard timeout < your endpoint's budget. Never "default" timeout (which is often 30–60 s on HTTP libs). Pick a number and justify it.
- **Retries.** Only on idempotent operations. Exponential backoff with jitter. Cap at 3 attempts. Non-idempotent call failures propagate to the caller as `transient` with `retryable=true` so the caller decides.
- **Circuit breaker.** If > N failures in window W, trip the breaker and fast-fail for cool-down period C. Libraries: `pybreaker`, `hystrix`, `gobreaker`. Don't hand-roll.
- **Never hold DB connection during external call.** Release, call, reacquire.

## 12. Async jobs & background work

Any operation > 2 s (email, heavy compute, external aggregation, report generation) MUST be queued:

- **Don't make the user wait.** Return `202 Accepted` with a job id; client polls or subscribes for result.
- **Job contract:** a job is a pure function of its payload. Jobs MUST be idempotent (same payload replayed → same result).
- **Dead letter queue.** After N retries, job moves to DLQ with full context. Alert on DLQ size > 0.
- **Observability.** Per-job `trace_id` propagates from the enqueueing request; job logs and HTTP logs correlate.

## 13. Audit events — high-value actions only

Write an audit row for high-value actions: subscription create/change/cancel, payment success/failure, refund, admin override, security-sensitive config change. Schema:

```
id | occurred_at | actor_type | actor_id | action | subject_type | subject_id | summary | correlation_id
```

NEVER put secrets / PII in the summary. Audit rows are read by support, compliance, and ops — they must be safe to render on a dashboard.

Anti-pattern: writing an audit row for every GET. Audit volume should correlate with state change, not traffic.

## 14. Request validation — at the edge, once

Validate once, at the HTTP boundary, using the framework's schema system (Pydantic, DRF Serializer, go-playground/validator, class-validator). Downstream services assume valid input.

Reject on failure with `VALIDATION_ERROR` + field-level details so the client can show per-field feedback. No generic "invalid input" — list every failing field.

## 15. Rate limiting — for public endpoints

Any public endpoint (no auth, or user-auth without workspace scope) needs rate limiting. Strategy:

- Per-IP for unauthenticated endpoints.
- Per-user-id for authenticated endpoints.
- Burst + sustained (e.g., 20 req / 1 min burst, 200 req / 1 hour sustained).
- Return `429 Too Many Requests` with `Retry-After` header.

Store counters in Redis or the framework's rate-limit module. Never in application memory (breaks under horizontal scale).

## 16. Pre-commit / PR checklist

Before opening a PR touching a backend file:

- [ ] No N+1 (greped for `for .* in .*: .*db\.` / `for .* in .*: .*\.objects\.` patterns)
- [ ] Response envelope consistent with project registry
- [ ] Idempotency for mutation endpoints
- [ ] Index verified via `EXPLAIN ANALYZE` on the matching table
- [ ] Transaction wraps multi-table writes
- [ ] Logs step-numbered, PII redacted, `trace_id` plumbed
- [ ] External calls have explicit timeouts
- [ ] Unit tests for service; integration test for the handler happy path + one error path
- [ ] Migration is append-only and idempotent (if touched)

## References

Stack-specific specializations extend this skill via `depends_on: [backend-fundamentals]`:

- [src/templates/django/skills/python-django/SKILL.md](../../../templates/django/skills/python-django/SKILL.md)
- [src/templates/fastapi/skills/python-fastapi/SKILL.md](../../../templates/fastapi/skills/python-fastapi/SKILL.md)
- [src/templates/go/skills/go-patterns/SKILL.md](../../../templates/go/skills/go-patterns/SKILL.md)
- [src/templates/go-fiber/skills/go-fiber/SKILL.md](../../../templates/go-fiber/skills/go-fiber/SKILL.md)

Universal principles from [clean-code](../clean-code/SKILL.md) still apply — this skill does not relax any of them.
