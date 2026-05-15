<!-- domain:BACKEND | layer:reference | ssot:true | updated:2026-01-01 -->
# Fiber Engineering Rules

Purpose: Canonical rules for Fiber v2 backend code in this project.
Read when: Writing or reviewing any Go file under `src/backend/`.
Skip when: Task is frontend-only or infra-only (no Fiber code).
Read next: `docs/playbooks/fiber-service.md`, `docs/api-contracts/error-format.md`

> Nav: [Docs Index](../00-index.md)

## Handler Contract

Every handler returns `error` and follows this shape:

1. **Parse** — `c.BodyParser` / `c.QueryParser` / `c.ParamsParser`. On parse failure return `fiber.NewError(400, "invalid body")`.
2. **Validate** — `validate.Struct(&dto)` with `go-playground/validator` tags. Failure → `fiber.NewError(422, err.Error())`.
3. **Delegate** — call a service with `c.UserContext()`.
4. **Respond** — `c.Status(code).JSON(payload)` for success, `return err` for failure (the central `ErrorHandler` renders the envelope).

No handler calls the database directly. No handler runs business logic inline.

## Error Envelope

Every non-2xx response MUST match `docs/api-contracts/error-format.md`:

```json
{
  "error": {
    "code":    "unprocessable_entity",
    "message": "email: invalid format",
    "details": { "field": "email", "constraint": "email" }
  }
}
```

The central `ErrorHandler` wired into `fiber.New(fiber.Config{ErrorHandler: ...})` is the ONLY place response status codes are mapped to slugs. Service and handler code returns typed errors (`fmt.Errorf("…: %w", domain.ErrNotFound)`), not HTTP codes.

## Context Propagation

- `c.UserContext()` (or `c.Context()` in pre-v2.43 code) is the *only* context passed into downstream calls.
- Never `context.Background()` inside a handler scope — cancellations must flow from client disconnect all the way to the DB driver.
- Background workers get their own root context, cancelled via `app.ShutdownWithContext`.

## Middleware Order (fixed)

```
recover → requestid → logger → cors → compress → auth (per-group) → route
```

Business logic never lives in middleware. Middleware handles only: panic recovery, correlation, structured logging, CORS, compression, auth. Everything else is a service concern.

## Request DTOs

- Separate DTO types per endpoint (`CreateOrderDTO`, `UpdateOrderDTO`) — do NOT reuse domain models as request bodies.
- DTOs carry `validate` tags; domain models carry business invariants.
- The service receives the *validated* DTO and returns a domain type — not the DTO.

## Database Access

- Repositories own SQL. Never a query in a service or handler.
- Pool lifetime matches the app: injected via constructor, closed in `defer` before `ShutdownWithContext` returns.
- Prepared statements for hot-path queries — use `sqlx`, `pgx`, or `ent` consistently per project, never mixed.
- Transactions start at the service boundary, not the repository — commit/rollback decision belongs to business logic.

## Testing

- `app.Test(httptest.NewRequest(...))` is the canonical pattern — no external server, no HTTP client.
- Every handler ships with a table-driven test covering happy + at least two error paths (validation failure, service error).
- Test fixtures live in `testdata/`; reset the DB via `testmain.go` global setup, not per-test.
- No mocks for `*fiber.Ctx` — use the real app through `app.Test()`.

## Project Layout

```
src/backend/
├── cmd/api/main.go                    # app.Listen + shutdown
├── internal/
│   ├── handlers/<domain>.go           # Fiber handlers
│   ├── services/<domain>.go           # business logic
│   ├── repositories/<domain>_pg.go    # DB adapter
│   ├── models/<domain>.go             # domain types
│   └── middleware/{auth,logging}.go
├── pkg/                               # cross-service helpers (rare)
├── go.mod / go.sum
└── testdata/
```

`handlers → services → repositories → models` is the only allowed dependency direction. Back-edges break the architecture.

## Forbidden Patterns

- Parsing a body without validating it
- Calling `fiber.NewError(500, ...)` for a business error (use typed error + central handler)
- Using `context.Background()` inside a handler
- Package-level `var db *sql.DB`
- Goroutine launched from a handler without a cancellation path
- Skipping `recover` middleware (one panic kills the whole server)
