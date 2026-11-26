# API Design Pre-Launch Checklist

Run this list before merging an OpenAPI / GraphQL schema, and again before exposing the endpoint outside the org. Each item maps to a section of the api-design skill or its references.

## Contract Shape

- [ ] **OpenAPI / GraphQL schema authored from use case types** (not the other way around).
- [ ] **All status codes documented** — including 400, 401, 403, 404, 409, 422, 429, 500.
- [ ] **All error responses use the RFC 9457 ProblemDetails envelope** (`Content-Type: application/problem+json`).
- [ ] **Every error `code` is registered in `docs/errors/catalogue.yaml`**.
- [ ] **No `additionalProperties: true`** (or its GraphQL equivalent) — unknown fields are rejected at the boundary.
- [ ] **Field naming consistent with the project convention** (`snake_case` for this project).
- [ ] **Dates use RFC 3339 UTC strings** (`2026-04-26T14:30:00Z`).
- [ ] **Money uses integer minor units + currency string** (no floats, no implicit currency).
- [ ] **IDs are prefixed strings** (`ord_…`, `usr_…`, `lsn_…`).
- [ ] **`null` vs absent field semantics documented per field** when both can occur.

## Mutations

- [ ] **`Idempotency-Key` header accepted on every POST/PATCH/DELETE that mutates state**.
- [ ] **Idempotency storage exists** (`idempotency_keys` table or equivalent).
- [ ] **Body-hash collision handling**: same key + different body → 409 `idempotency_key_collision`.
- [ ] **In-flight collision handling**: same key arrives twice in parallel → second waits or returns retryable error.
- [ ] **5xx and timeouts NOT stored** as final responses (they are retryable).
- [ ] **Idempotency entries TTL'd** (24h default).
- [ ] **POST that creates returns 201 + `Location` header**.
- [ ] **DELETE returns 204 No Content** on success.

## List / Read

- [ ] **All list endpoints paginated** (no unbounded result sets).
- [ ] **Pagination is cursor-based** unless documented otherwise.
- [ ] **`limit` parameter has a hard max** (100 default; reject larger).
- [ ] **`next_cursor: null` + `has_more: false`** on the last page.
- [ ] **Cursor is an opaque base64 token** (clients don't parse it).
- [ ] **Cursor encodes a stable sort tuple** (e.g., `(created_at, id)`) so ties don't cause skips/duplicates.
- [ ] **No `total` count returned** unless cached separately.
- [ ] **Filter / sort / project params documented**.

## Headers

- [ ] **`X-Request-Id` echoed back** on every response.
- [ ] **`Content-Type: application/json`** on JSON, **`application/problem+json`** on errors.
- [ ] **`Content-Encoding: gzip`** for responses >1KB.
- [ ] **`Cache-Control` set explicitly** on every endpoint (even if `no-store`).
- [ ] **`ETag` set on cacheable resources** + 304 returned for matching `If-None-Match`.
- [ ] **`RateLimit-Limit / RateLimit-Remaining / RateLimit-Reset` on every authenticated response**.
- [ ] **`Retry-After` on every 429 / 503**.
- [ ] **`Vary: Authorization, Accept-Language, Accept-Encoding`** when responses depend on these.
- [ ] **`WWW-Authenticate` on 401**.

## Security

- [ ] **Auth scheme documented** (Bearer + JWT? Cookie session? both?).
- [ ] **Per-endpoint scopes / permissions documented** (and enforced).
- [ ] **No PII in URL paths or query params** (logs, browser history, referrers).
- [ ] **No secrets in error responses** (never `str(exc)` in `detail`).
- [ ] **No internal identifiers leaked** (table names, column names, file paths, stack traces).
- [ ] **Request size limits set** (1MB default, raise per-endpoint with rationale).
- [ ] **Rate limits set per endpoint** (not just global).
- [ ] **CORS origins explicit** (no `*` for endpoints that read auth headers).
- [ ] **`Strict-Transport-Security` header on TLS responses**.
- [ ] **TLS-only**: redirect or refuse HTTP at the LB.

## Versioning + Deprecation

- [ ] **Versioning strategy documented** (tolerant reader / URL / header).
- [ ] **Breaking changes tracked**: a CI tool (`oasdiff`, `graphql-inspector`) compares schema vs main on every PR.
- [ ] **`Deprecation` header (RFC 9745) sent on deprecated fields/endpoints** with sunset date.
- [ ] **Sunset timeline communicated** (≥6 months for public APIs).
- [ ] **Old version kept alive long enough** for the slowest consumer to migrate.

## Testing

- [ ] **Schema lint passes** (`spectral lint`).
- [ ] **Mock server runs** (`prism mock openapi.yaml`) — frontend can develop against it.
- [ ] **Property-based contract tests run in CI** (`schemathesis`).
- [ ] **Snapshot tests of happy + sad responses checked into repo**.
- [ ] **Codegen happens in CI** — drift between server + clients is caught at PR time.

## Observability

- [ ] **`X-Request-Id` propagated through downstream calls** (set if missing at edge).
- [ ] **Per-endpoint metrics**: count, P50/P95/P99 latency, error rate.
- [ ] **Per-endpoint logs include** `request_id`, `user_id`, `endpoint`, `status`, `latency_ms`, `code` (on errors).
- [ ] **No PII in logs** (mask emails, omit secrets, hash where needed for grouping).
- [ ] **Slow-query log threshold set** (e.g. responses >500ms get their query plan attached).
- [ ] **Trace context propagated** (W3C Trace-Context header).

## Documentation

- [ ] **Endpoint has a one-line `summary`** in the spec.
- [ ] **Endpoint has a longer `description` with at least one example use case**.
- [ ] **Each request body field has `description` + `example`**.
- [ ] **Each error code links to its catalogue entry**.
- [ ] **`/docs` (Swagger UI / GraphQL Playground) renders without errors**.
- [ ] **Public-facing changelog updated** with the new endpoint and any breaking changes.

## Mobile-Specific (this project's RN client)

- [ ] **No offline-incompatible patterns** (no required real-time state for read endpoints).
- [ ] **Response sizes bounded** — paginate aggressively; mobile cellular is precious.
- [ ] **Conditional GET (ETag) supported** on cacheable endpoints — RN can persist + revalidate.
- [ ] **Idempotency-Key MANDATORY on every mutation** — RN retries are the entire reason this header exists.
- [ ] **Image / file URLs are CDN-served**, with `Cache-Control: max-age=31536000, immutable` for hashed assets.
- [ ] **Avoid pre-signed URLs that expire in <1h** if mobile may be backgrounded.

---

**The shortest path to a healthy API**: copy this list into the PR template for new-endpoint PRs. Every box must be checked or explicitly waived with a reason in the PR description.
