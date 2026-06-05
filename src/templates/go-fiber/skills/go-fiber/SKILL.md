---
name: go-fiber
description: Use when creating or modifying Go files under src/backend/ in a Fiber project — handlers, middleware, request validation, graceful shutdown, and table-driven tests with app.Test(). Triggers on any .go file change under src/backend/. Covers idiomatic Fiber v3 (GA 2026, Go 1.25+) patterns plus the Go fundamentals (error wrapping, context propagation, struct tags for validation); see references/fiber-v3-patterns.md for the v2→v3 changes.
globs: "src/backend/**/*.go"
depends_on:
  - clean-code
  - backend-fundamentals
last_reviewed: "2026-06-04"
versions_ref: versions.json

---

REQUIRED BACKGROUND: This skill `depends_on: [clean-code, backend-fundamentals]`. Both are loaded transitively — `clean-code` gives universal code quality, `backend-fundamentals` gives stack-agnostic backend patterns (services/selectors, idempotency, envelopes, N+1, migrations, auth). This skill adds ONLY Fiber-specific layering on top.

## Pre-Code Checklist

- [ ] Read `docs/engineering/fiber-rules.md` — canonical Fiber policy
- [ ] If touching HTTP handlers: read `docs/playbooks/fiber-service.md`
- [ ] If touching request parsing: read `docs/api-contracts/error-format.md`
- [ ] Confirm Fiber version in `go.mod` (v2 assumed unless stated otherwise)
- [ ] `go vet ./...` clean before editing

## Handler Pattern

Every handler has the same signature and lifecycle:

```go
func ListOrders(svc *service.Orders) fiber.Handler {
    return func(c *fiber.Ctx) error {
        // 1. Parse + validate
        var q ListQuery
        if err := c.QueryParser(&q); err != nil {
            return fiber.NewError(fiber.StatusBadRequest, "invalid query")
        }
        if err := validate.Struct(&q); err != nil {
            return fiber.NewError(fiber.StatusUnprocessableEntity, err.Error())
        }

        // 2. Call the service with a context (cancellation propagates)
        orders, err := svc.List(c.UserContext(), q)
        if err != nil {
            return err  // central error handler renders the envelope
        }

        // 3. Respond
        return c.Status(fiber.StatusOK).JSON(fiber.Map{
            "data": orders,
            "meta": fiber.Map{"count": len(orders)},
        })
    }
}
```

**Rules:**
- No business logic inside the handler. Orchestrate only.
- No direct DB calls. Handler → service → repository.
- Always pass `c.UserContext()` downstream — never `context.Background()`.

## Error Envelope

Central error handler in `app.Config{}`:

```go
app := fiber.New(fiber.Config{
    ErrorHandler: func(c *fiber.Ctx, err error) error {
        code := fiber.StatusInternalServerError
        msg  := "internal error"
        if e, ok := err.(*fiber.Error); ok {
            code = e.Code
            msg  = e.Message
        }
        return c.Status(code).JSON(fiber.Map{
            "error": fiber.Map{
                "code":    statusToSlug(code),
                "message": msg,
                "details": extractDetails(err),
            },
        })
    },
})
```

Typed errors at the service layer (`fmt.Errorf("…: %w", ErrNotFound)`) translate to HTTP codes via the middleware — never hand-code status codes in service code.

## Middleware Stack (in order)

```go
app.Use(recover.New())         // panic → 500, don't crash the process
app.Use(requestid.New())       // X-Request-ID for correlation
app.Use(logger.New(logger.Config{ /* structured */ }))
app.Use(cors.New())
app.Use(compress.New())
// group-specific below:
auth := app.Group("/api", middleware.Auth(jwtSecret))
auth.Get("/orders", ListOrders(svc))
```

**Never** put business logic in middleware. Middleware handles cross-cutting concerns only (auth, logging, rate-limit).

## Validation

Use `go-playground/validator` via struct tags on DTOs:

```go
type CreateOrderDTO struct {
    UserID    string  `json:"user_id"    validate:"required,uuid4"`
    Amount    float64 `json:"amount"     validate:"required,gt=0"`
    Currency  string  `json:"currency"   validate:"required,len=3,uppercase"`
}
```

Validation failure → 422 (UnprocessableEntity), not 400. 400 is for malformed JSON only.

## Graceful Shutdown

```go
func main() {
    app := buildApp()
    go func() { _ = app.Listen(":8080") }()

    quit := make(chan os.Signal, 1)
    signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
    <-quit

    ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
    defer cancel()
    _ = app.ShutdownWithContext(ctx)
}
```

Every long-running process in the app (background workers, DB pool, queue consumers) must respect the same shutdown context.

## Testing

Use Fiber's built-in `app.Test()` — no external server needed, no `httptest` mocking:

```go
func TestListOrders_ok(t *testing.T) {
    app := newTestApp(t)
    req := httptest.NewRequest("GET", "/api/orders?limit=5", nil)
    req.Header.Set("Authorization", "Bearer "+testJWT(t))

    res, err := app.Test(req, fiber.TestConfig{Timeout: 2 * time.Second})
    require.NoError(t, err)
    assert.Equal(t, 200, res.StatusCode)

    var body struct{ Data []Order }
    require.NoError(t, json.NewDecoder(res.Body).Decode(&body))
    assert.Len(t, body.Data, 5)
}
```

**Table-driven for variants:**

```go
cases := []struct {
    name   string
    query  string
    status int
}{
    {"ok",       "?limit=5",        200},
    {"invalid",  "?limit=-1",       422},
    {"too_big",  "?limit=10000",    422},
}
for _, tc := range cases {
    t.Run(tc.name, func(t *testing.T) { /* … */ })
}
```

## Project Layout

```
src/backend/
├── cmd/api/main.go          # app.Listen
├── internal/
│   ├── handlers/            # Fiber handlers — orchestration only
│   ├── services/            # business logic, context-propagating
│   ├── repositories/        # DB access, sqlx / pgx / ent
│   ├── models/              # domain types + validator tags
│   └── middleware/          # auth, cors, requestid
├── pkg/                     # reusable across services (rare)
├── go.mod
└── go.sum
```

Never import `handlers` from `services` (back-edge). Services are the leaf of the dependency DAG; handlers depend on services.

## Anti-Patterns (hard no)

- `c.BodyParser(&req)` without follow-up `validate.Struct(&req)`
- Returning `fmt.Errorf("bad request")` from a handler — use `fiber.NewError(status, msg)` so the central handler picks up the code.
- Using `context.Background()` inside handler scope — always `c.UserContext()`.
- Mixing goroutines with Fiber without a context-derived cancellation.
- Global DB pool held in a package-level `var db *sql.DB` — inject it via the service constructor.

## Deepening + tooling

- [references/fiber-v3-patterns.md](references/fiber-v3-patterns.md) — Fiber v3 (2026) handlers, binding, central error handler, middleware order, fasthttp gotchas.
- [references/anatomy.md](references/anatomy.md) — file map + scaffold; `scripts/new_endpoint.py` to generate one.
- [assets/fiber-checklist.md](assets/fiber-checklist.md) — the review gate.
- Versions pinned in [versions.json](versions.json) — `make skills-check-versions`.
