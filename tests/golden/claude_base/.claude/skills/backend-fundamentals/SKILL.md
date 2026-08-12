---
name: backend-fundamentals
tier: layer
domain: [backend]
description: Stack-agnostic backend patterns. Use when writing or modifying any server-side code (HTTP handler, DB query, background job, auth/middleware, webhook) regardless of language or framework. Covers services/selectors split, idempotency, error envelopes, migration discipline, N+1 avoidance, scale-aware design, auth guardrails, concurrency and race conditions on contended writes, and logging hygiene.
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
last_reviewed: "2026-08-12"

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
- User-initiated → key = `Idempotency-Key` header (`draft-ietf-httpapi-idempotency-key-header`).

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

## 15. Rate limiting — every route, composite key

**Every route resolves a policy.** Declare the budget next to the handler; a route that declares none inherits a restrictive global fallback. Never a hand-maintained list of "the public ones" — the failure mode is a missing line, and missing lines are invisible in a diff. Add a test that walks the router and fails on any route resolving no policy.

**The key is a tuple, and every applicable policy is evaluated — deny if any one is exhausted.** `key = user_id if authenticated else ip` is the anti-pattern: it lets an attacker with 5,000 free accounts escape the IP limit, and an IP-rotating attacker escape the account limit.

| Dimension | Source | Note |
|---|---|---|
| policy / route | route declaration | namespaces the counter; version it so a retune doesn't inherit old counts |
| principal | user / org id | survives IP rotation — a proxy pool cannot shed it |
| api key / client id | credential | the tenant's key, not their end users' |
| session / device | signed cookie, device id | survives IP churn on mobile |
| ip prefix | trusted-proxy hop (below) | never the only dimension on a human-reachable route |

- **Resolve the IP from a hop you own.** Configure a trusted-proxy CIDR set or hop count, join *all* `X-Forwarded-For` headers into one list, walk from the **rightmost** entry skipping trusted proxies, take the first untrusted address. `xff.split(',')[0]` lets one attacker mint unlimited distinct keys — the limiter reports healthy while enforcing nothing.
- **Mask IPv6 to /64** (plus a looser /48 policy), and normalize spelling before hashing. A residential customer is delegated the whole /64, so per-address keying hands them 2^64 free buckets.
- **CGNAT cuts the other way** — thousands of unrelated users share one IPv4. When only the IP dimension trips, prefer a challenge / step-up over a hard block.

**Algorithm: token bucket (capacity = burst, refill = sustained), GCRA, or sliding window — not fixed-window.** 100 requests at `:59` plus 100 at `:01` is 200 in two seconds, doubling the budget you thought you set.

**One atomic decision per dimension** — a single Lua `EVAL` / `FCALL` returning allow + remaining + reset in one round trip. Read-then-write lets N workers each admit, so the effective limit scales with worker count; computing header values in a second call reports a budget that disagrees with the decision just made. Independent dimensions cannot share a script: they have no common key, and forcing one (by hash-tagging on principal) scopes the IP counter *per principal* and silently deletes the dimension you added it for. Co-locate only same-dimension keys — one counter's burst and sustained windows.

**Store:** a dedicated Redis/Valkey db or instance with `maxmemory-policy noeviction`, keys `rl:<policy>:<version>:<hash>`. Note the angle brackets: `{…}` is literal Redis Cluster hash-tag syntax, and only the text inside the first pair is hashed, so a `{policy}` template pins every counter for that policy to one slot. Never the `allkeys-lru` cache instance — it evicts counters under memory pressure, i.e. exactly during the spike. Never application memory (breaks under horizontal scale).

**Fail-open vs fail-closed is per policy, never global.** Capacity/fairness limiters fail open — a limiter outage must not become an API outage. Login, OTP-send, password-reset, payment, and paid-third-party limiters fail **closed** or degrade to a challenge; a blanket "if Redis is down, allow" is an open credential-stuffing window.

**Charge cost, not requests.** Debit units proportional to the work (page size, export, fan-out, LLM tokens) *before* doing it — a uniform limit prices `?limit=1` and `?limit=10000` identically. Every paid third-party call also gets a hard spend cap.

**Auth endpoints** get a per-account limiter keyed on the submitted identifier, independent of any IP dimension, incremented on **failed** attempts only (counting successes locks a user out of their own account), with `send` throttled separately from `verify`.

**Response contract** — 429 + `Retry-After` no earlier than the window end, `RateLimit-*` on successful responses too: see [api-design](../api-design/SKILL.md). Client-side debounce is UX only and never justifies a weaker server limit. On 429 the client waits the **full** `Retry-After` and adds jitter on top — `sleep = retry_after + random(0, spread)`; a jitter that can resolve to zero retries immediately, hammering the limiter the header just asked it to respect. With no header, fall back to `random(0, min(cap, base * 2^attempt))`.

**Ship a new or retuned limiter in shadow mode** — log-only, behind a kill switch, emitting a decision counter labeled by policy, route, and which dimension tripped. Without that label a wrong budget and a real attack look identical at 3 a.m.

## 16. Concurrency — contended writes

Any read whose result decides a later write is **check-then-act (TOCTOU)** and is a defect unless both happen in one statement or under a lock/constraint held across both. Recognize it by shape: `if available`, `if not exists`, `if balance >=`, `if count() < limit`, any ORM `get()` → mutate → `save()`. No type system, linter, or sequential test marks it — 500 buyers all read `stock=1`, all write `stock=0`, one ticket sells 500 times, nothing is logged.

**Escalate in order; state in the PR why the cheaper rung was insufficient. Never open at rung 5.**

| # | Rung | Use when |
|---|---|---|
| 1 | Atomic conditional write — `UPDATE inventory SET stock = stock - 1 WHERE id = $1 AND stock >= 1` | One row, guard expressible as a predicate. **Default.** |
| 2 | `SELECT … FOR UPDATE` on one row, one short tx | App logic must run between the read and the write |
| 3 | `UNIQUE` / `EXCLUDE` constraint, insert and catch duplicate-key | "at most one per X" — one redemption per user, no overlapping bookings |
| 4 | `SERIALIZABLE` + retry | Invariant spans rows a lock can't cover (SUM vs cap, row doesn't exist yet) |
| 5 | External lock service (Redis / etcd) | The contended resource isn't in the DB at all |

- **Check the affected-row count on every guarded or version-checked write.** 0 rows raises nothing — it is a successful UPDATE that matched nothing. Map 0 → `409 sold_out` / `412 stale_version`; never read "no exception" as success. Skipping it captures the card for stock that was never decremented.
- **The constraint is the guarantee; the app pre-check is an optimization.** Postgres will not serialize concurrent inserts into a table with no unique index. Insert, catch the violation, return the idempotent success or 409 — a `catch IntegrityError` that 500s is the same bug wearing a different status code.
- **Rung 4 is write skew:** two transactions each read a set, each verify "still under the cap", each insert a *different* row, both commit. Row locks and `REPEATABLE READ` do not stop it — you cannot `FOR UPDATE` a row that doesn't exist yet. Verify the engine default before assuming (Postgres `READ COMMITTED`, MySQL/InnoDB `REPEATABLE READ`); isolation-level and optimistic-locking SQL lives in [db-design](../db-design/SKILL.md).
- **Retry the whole transaction, not the statement.** Catch SQLSTATE `40001` (serialization — also InnoDB's deadlock code) and Postgres-only `40P01` (deadlock), re-run from `BEGIN` including every read, cap attempts, back off with jitter (§11). Reusing a value read during the aborted attempt re-introduces the anomaly you paid for.
- **A row lock may not span an external call (§7) — commit a short reservation instead:** `status='held', expires_at = now() + '10 minutes'`, and sweep expired holds.
- **A distributed lock without a fencing token is best-effort only.** A lease expires while its holder is GC-paused → two holders believe they hold it. Unless the protected resource stores a monotonic token and rejects older ones, label the lock efficiency-only in code and put the real invariant at rung 1–4.
- **Client-side guards are UX, not correctness.** The disabled submit button is set after the request is already in flight, and cannot suppress StrictMode double-invoke, mobile retry-on-network-change, or back-then-resubmit. The defense is rung 1–4 or an idempotency key (§3).

**Test it or it isn't done.** Fire N ≥ 5× available units of *real parallel* requests at a *real* DB seeded with exactly one unit; assert `successes == initial_stock`, `final_stock >= 0`, and that the losers got the intended 409 — not a 500. Repeat 20–50× in CI: a single run passes by luck, and a mocked repo passes on broken code by construction. Run the suite under the language race detector (`go test -race`, TSan) wherever the process holds shared mutable state.

## 17. Pre-commit / PR checklist

Before opening a PR touching a backend file:

- [ ] No N+1 (greped for `for .* in .*: .*db\.` / `for .* in .*: .*\.objects\.` patterns)
- [ ] Response envelope consistent with project registry
- [ ] Idempotency for mutation endpoints
- [ ] Index verified via `EXPLAIN ANALYZE` on the matching table
- [ ] Transaction wraps multi-table writes
- [ ] Logs step-numbered, PII redacted, `trace_id` plumbed
- [ ] External calls have explicit timeouts
- [ ] Every touched route resolves a rate-limit policy; key is composite, not IP-or-user
- [ ] Unit tests for service; integration test for the handler happy path + one error path
- [ ] Migration is append-only and idempotent (if touched)
- [ ] Contended write uses the lowest sufficient rung; affected-row count checked
- [ ] Concurrent-invariant test exists for any contended path

## References

Stack-specific specializations extend this skill via `depends_on: [backend-fundamentals]` — your project's stack skill (python-django / python-fastapi / go-patterns / go-fiber) is present when that stack is installed.

## Tooling

Flag framework/ORM leakage into domain/service code (keep the core framework-free):
`python3 scripts/check_layering.py src/backend/services/*.py`

## See also

- [references/backend-patterns.md](references/backend-patterns.md) — layering, idempotency, errors, N+1, migrations.
- [assets/backend-checklist.md](assets/backend-checklist.md) — the review gate.
- [hexagonal-architecture](../hexagonal-architecture/SKILL.md) · [api-design](../api-design/SKILL.md) · [sql-authoring](../sql-authoring/SKILL.md).

Universal principles from [clean-code](../clean-code/SKILL.md) still apply — this skill does not relax any of them.

Cross-service code placement: promote a helper reused by a second service into `src/shared/<lang>/`, and route cross-language types through `src/shared/contracts/` only — see [clean-code](../clean-code/SKILL.md) § 7 and the `docs/engineering/project-anatomy.md` SSOT.
