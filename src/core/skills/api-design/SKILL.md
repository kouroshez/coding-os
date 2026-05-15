---
name: api-design
description: Design HTTP / REST / GraphQL API contracts that survive multiple consumers and years of evolution. Use when defining a new endpoint, reviewing an OpenAPI spec, evolving a public API, debating REST vs GraphQL, deciding versioning strategy, designing pagination or idempotency keys, or shaping error envelopes. Paired with hexagonal-architecture (the use case is the contract; the API is its translation).
tier: cross-cutting
domain: [backend]
last_reviewed: "2026-05-11"

---

# API Design — REST + GraphQL Contracts

A practical guide to designing APIs that consumers can build against without surprises. Stack-agnostic; concrete patterns target this project's stack (Go+Fiber for the business backend, Python+FastAPI for the AI adapter, React Native client).

## When to Use This Skill

- Adding the first endpoint to a service — the contract you ship now will outlive three implementations.
- Reviewing an OpenAPI / GraphQL schema PR before merge.
- Adding a v2 version of a live endpoint without breaking v1 clients.
- Debating REST vs GraphQL for a new bounded context.
- Designing pagination, idempotency, rate-limit responses, batch endpoints.
- Mapping domain errors (from a use case in your hexagonal architecture) to HTTP responses.

Skip when: writing internal-only RPCs that have one caller and you control both sides — use whatever's fastest.

## The Contract Is the Product

Three rules that override everything else:

1. **Consumers cannot read your code.** They read the contract. If the contract is ambiguous, the consumer guesses wrong, and you find out in production.
2. **Breaking changes are expensive forever.** Every consumer must coordinate. Plan as if you can't break things — because at scale, you can't.
3. **The use case shape is sacred. The API shape is negotiable.** Don't bend domain operations to match HTTP idioms. Translate at the adapter boundary (per hexagonal-architecture).

## REST vs GraphQL — Decision

Pick **REST** when:
- Consumers are heterogeneous (mobile + web + 3rd-party). REST is the universal lingua franca.
- Endpoints map cleanly to resources. CRUD-like dominates.
- You need HTTP-native caching (CDN, proxies, conditional GET).
- You want minimal client tooling (no codegen mandatory).

Pick **GraphQL** when:
- Single consumer team or tightly-coupled clients (e.g. one mobile app + one web app from same team).
- Heavy over-fetching with REST: clients pull 12 fields and use 2.
- Frequent shape evolution that doesn't justify a v2 endpoint.
- You're willing to invest in DataLoader, persisted queries, query complexity limits.

**For this project**: REST is the right default for both backends. RN is the only consumer; the cost of GraphQL machinery does not pay off yet.

For the patterns and pitfalls of each, see [references/rest-contracts.md](references/rest-contracts.md) and [references/graphql-contracts.md](references/graphql-contracts.md).

## Contract-First Workflow

Authoring order, in this exact sequence:

1. **Use case first.** The hexagonal use case has an Input DTO and an Output DTO. Those types ARE the source of truth. Write them before the API.
2. **OpenAPI / GraphQL schema next.** Hand-write or generate from use case types. Do **not** hand-write Go/Python types from a schema someone else drafted.
3. **Request/response samples.** Write 3 happy + 2 sad payloads in the spec. Code reviewers check these, not your prose.
4. **Mock server.** OpenAPI → Prism / GraphQL → mock resolvers. Frontend builds against the mock; backend implements against the same spec.
5. **Contract tests in CI.** Schemathesis (REST) / GraphQL-inspector (GraphQL). Catch drift before merge.
6. **Implementation.** Last step. The schema is the spec; the code is the impl.

## Versioning — Pick One Strategy and Stick to It

Three strategies, ordered by maintenance cost (cheapest → most expensive):

### Tolerant reader, no version (best for additive change)

Server adds new fields freely. Old clients ignore unknown fields. Old fields stay forever once added.

- **Pros**: zero version coordination, zero v2 migration.
- **Cons**: cannot remove or rename fields. Schema accretes.
- **When**: most internal APIs, mobile apps you control end-to-end (RN here qualifies).

### URL versioning (`/v1/orders`, `/v2/orders`)

Two parallel routes; clients pick.

- **Pros**: trivial routing, clear in logs/CDN.
- **Cons**: doubles surface area, doubles tests, doubles docs.
- **When**: public APIs with external consumers you can't coordinate with.

### Header versioning (`Accept: application/vnd.app.v2+json`)

Same URL, different versions via content negotiation.

- **Pros**: clean URL, versions per resource.
- **Cons**: hard to debug, CDNs need to vary on header, harder for newcomers.
- **When**: rare. Hypermedia APIs.

**For this project**: tolerant reader by default. Promote to URL versioning the day you sign your first 3rd-party integration.

## Idempotency — Mutations Must Be Replayable

Every mutating endpoint (`POST`, `PUT`, `PATCH`, `DELETE`) MUST accept and honor an `Idempotency-Key` header. Why: networks drop responses; clients retry; you cannot tell a duplicate from a fresh request without it.

```
POST /orders
Idempotency-Key: 8e0f7b1d-2a44-4c7f-9b2e-1c5d6e7f8a9b
Content-Type: application/json

{ "items": [...] }
```

Server behavior:

1. First call with `key=K` → execute, store `(K, response)` for 24h.
2. Subsequent call with same `key=K` → return stored response, do NOT re-execute.
3. Stored response includes status code, headers, body.

Stripe-style. Industry standard since ~2015. Do not skip this.

For the implementation pattern (DB schema for the idempotency table, in-flight collision handling, key TTL), see [references/idempotency-pagination.md](references/idempotency-pagination.md).

## Pagination — Cursor by Default

Three options; pick by data shape:

| Style | Use when | Avoid when |
|---|---|---|
| **Cursor** (opaque token) | Datasets that grow over time, ordered list, infinite scroll. | Random page jumps required. |
| **Offset** (`?page=3`) | Small fixed datasets, admin grids with "go to page N" UX. | Large or growing datasets — slow + race-prone. |
| **Keyset** (`?after_id=123`) | Strictly time-ordered, simple. | Multi-column ordering. |

Cursor is the default for this project's RN client (infinite scroll lists). Pattern in [references/idempotency-pagination.md](references/idempotency-pagination.md).

## Error Envelope — RFC 9457 Problem Details

One envelope across the entire API surface. Every error response, every endpoint, every version. Spec: [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457.html) (replaces RFC 7807, ratified 2024).

Minimal shape:

```json
{
  "type": "https://api.app.com/problems/insufficient-funds",
  "title": "Insufficient funds",
  "status": 402,
  "detail": "Account balance is $4.20; required $42.00.",
  "instance": "/payments/pay_123",
  "code": "insufficient_funds",
  "errors": [
    { "field": "amount", "code": "exceeds_balance", "message": "..." }
  ]
}
```

Rules:

- **`type`** is a stable URL identifying the error class. Treat as the primary key for client switch logic.
- **`code`** is a short machine token (`insufficient_funds`, `validation_failed`). Stable. Snake_case.
- **`title`** is a one-line human summary. Frozen for a given `type`.
- **`detail`** can vary per occurrence — actual numbers, names, etc. Safe to show users.
- **`errors[]`** carries field-level validation breakdown. Empty/omitted for non-validation errors.
- **Never `str(exc)`** in `detail`. Strip stack traces, SQL fragments, file paths.

Full mapping table (domain exception → HTTP status → envelope) in [references/error-envelope.md](references/error-envelope.md).

## Status Code Discipline

Common ones, with the most-misused calls highlighted:

| Code | Meaning | Common misuses |
|---|---|---|
| 200 | OK with body | Used for "created" — should be 201. |
| 201 | Created — must include `Location` header | Forgetting `Location`. |
| 202 | Accepted — async, will process later | Used for sync ops. |
| 204 | No content (DELETE success, idempotent PUT) | Including a body anyway. |
| 400 | Validation failed | Used for auth failures (should be 401/403). |
| 401 | Not authenticated | Used when authenticated but lacks permission (should be 403). |
| 403 | Authenticated but forbidden | Used to hide existence (should be 404 then). |
| 404 | Not found OR hiding existence | Used for "deleted" (should be 410). |
| 409 | Conflict (duplicate, lost update) | Used for validation (should be 400/422). |
| 410 | Gone — was here, deleted | Rarely used; defaults to 404. |
| 422 | Semantically invalid (parsed OK, business rule failed) | Used for syntax errors (should be 400). |
| 429 | Rate-limited — must include `Retry-After` | Forgetting `Retry-After`. |
| 500 | Unexpected server error | Used for known errors (should be 4xx). |
| 503 | Temporarily unavailable | Used for permanent failures. |

Default: **400 for "client did something wrong with the request shape"**, **422 for "request is well-formed but violates a business rule"**.

## Rate Limiting Headers

Every authenticated endpoint should expose three headers on every response (RFC 9239 / IETF draft, near-universal practice):

```
RateLimit-Limit: 100
RateLimit-Remaining: 47
RateLimit-Reset: 1745678901
```

On 429 responses, also include `Retry-After: 60` (seconds) so clients know when to retry.

## Cross-Cutting Headers

| Header | Direction | Purpose |
|---|---|---|
| `X-Request-Id` | both | Correlation across services. Generate at edge if absent. |
| `X-Idempotency-Key` | request | See above. |
| `If-Match` / `If-None-Match` | request | Optimistic concurrency (ETags). |
| `Cache-Control` | response | Even if you don't cache, send `no-store` explicitly for sensitive endpoints. |
| `Content-Encoding` | response | Always gzip/brotli responses >1KB. |

## Common Anti-Patterns (full list in references/rest-contracts.md)

1. **Verbs in URLs** — `POST /createOrder` instead of `POST /orders`.
2. **Mixed casing** — `userId` in body, `user_id` in query string. Pick one project-wide.
3. **Tunneling everything through POST** — using POST for reads "because complex query".
4. **Returning 200 with `{"success": false}`** — use the right status code.
5. **HTTP error in 200 body** — same.
6. **Missing pagination on list endpoints** — works in dev, OOMs in prod.
7. **Date strings without timezone** — always `2026-04-26T14:30:00Z` (RFC 3339).
8. **Boolean string values** — `"true"` vs `true`. Use real JSON booleans.
9. **`null` vs absent field semantic confusion** — document explicitly.
10. **Inconsistent error shape per endpoint** — pick one envelope, use everywhere.

## Testing the Contract

Three layers, each catching different drift:

1. **Schema tests** — OpenAPI + spectral lint, GraphQL + graphql-inspector. Catches malformed spec before merge.
2. **Contract tests** — Schemathesis (REST) / Pact (consumer-driven). Hits live server with property-based requests.
3. **Snapshot tests** — record happy + sad responses, diff in CI. Catches accidental shape change.

For Go: `oapi-codegen` validates handlers against spec. For FastAPI: built-in `/openapi.json` is the spec — generate client from it. For RN: codegen from OpenAPI → typed client (`openapi-typescript-codegen`).

## Source Material

- *Web API Design: The Missing Link* (Apigee, free) — the foundational pamphlet.
- RFC 9457 — Problem Details for HTTP APIs (2024 update).
- RFC 9239 / draft-ietf-httpapi-ratelimit-headers.
- Stripe API docs — gold standard for REST + idempotency + pagination.
- GitHub REST API v3 + GraphQL v4 docs — the largest dual-flavor live API.
- *Designing APIs with Swagger and OpenAPI* (Manning, 2024) — current OpenAPI 3.1 patterns.
