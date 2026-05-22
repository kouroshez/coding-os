<!-- domain:BACKEND | layer:playbook | ssot:true | updated:2026-01-01 -->
# Fiber Service Playbook

Purpose: End-to-end workflow for adding or changing a Fiber HTTP endpoint.
Read when: Starting any task that touches `src/backend/internal/handlers/**` or adds a new route group.
Skip when: Task is infra-only, test-only, or doesn't touch HTTP surface.
Read next: `docs/engineering/fiber-rules.md`, `docs/api-contracts/error-format.md`

> Nav: [Docs Index](../00-index.md)

## Read-Pack (max 6 files)

1. `docs/playbooks/fiber-service.md` — this playbook
2. `docs/engineering/fiber-rules.md` — rules
3. `docs/api-contracts/error-format.md` — error envelope
4. `src/backend/internal/handlers/<existing-similar>.go` — closest existing handler
5. `src/backend/internal/services/<existing-similar>.go` — its service
6. `src/backend/cmd/api/main.go` — where the route is registered

Do not read more than these. If something's missing, grep for it.

## Ordered Steps

### 1 — Define the DTO

Add a typed request + response struct in `internal/handlers/<domain>_dto.go`:

```go
type CreateOrderRequest struct {
    UserID   string  `json:"user_id"   validate:"required,uuid4"`
    Amount   float64 `json:"amount"    validate:"required,gt=0"`
    Currency string  `json:"currency"  validate:"required,len=3,uppercase"`
}

type CreateOrderResponse struct {
    ID        string    `json:"id"`
    Status    string    `json:"status"`
    CreatedAt time.Time `json:"created_at"`
}
```

### 2 — Write the service method

`internal/services/orders.go`:

```go
func (s *Orders) Create(ctx context.Context, dto CreateOrderRequest) (*model.Order, error) {
    if err := s.users.Exists(ctx, dto.UserID); err != nil {
        return nil, fmt.Errorf("users.Exists: %w", err)
    }
    order := model.NewOrder(dto.UserID, dto.Amount, dto.Currency)
    if err := s.repo.Insert(ctx, order); err != nil {
        return nil, fmt.Errorf("repo.Insert: %w", err)
    }
    return order, nil
}
```

Errors wrap with `%w` so the central handler + `errors.Is` work.

### 3 — Write the handler

`internal/handlers/orders.go`:

```go
func CreateOrder(svc *service.Orders) fiber.Handler {
    return func(c *fiber.Ctx) error {
        var req CreateOrderRequest
        if err := c.BodyParser(&req); err != nil {
            return fiber.NewError(fiber.StatusBadRequest, "invalid body")
        }
        if err := validate.Struct(&req); err != nil {
            return fiber.NewError(fiber.StatusUnprocessableEntity, err.Error())
        }
        order, err := svc.Create(c.UserContext(), req)
        if err != nil {
            return err
        }
        return c.Status(fiber.StatusCreated).JSON(CreateOrderResponse{
            ID:        order.ID,
            Status:    order.Status,
            CreatedAt: order.CreatedAt,
        })
    }
}
```

### 4 — Register the route

`cmd/api/main.go`:

```go
orders := app.Group("/api/orders", middleware.Auth(jwt))
orders.Post("/", handlers.CreateOrder(services.Orders))
```

### 5 — Write the table-driven test

`internal/handlers/orders_test.go`:

```go
func TestCreateOrder(t *testing.T) {
    cases := []struct {
        name   string
        body   string
        status int
    }{
        {"ok",         `{"user_id":"…","amount":10.5,"currency":"USD"}`, 201},
        {"bad_json",   `{`,                                              400},
        {"bad_amount", `{"user_id":"…","amount":-1,"currency":"USD"}`,   422},
    }
    app := newTestApp(t)
    for _, tc := range cases {
        t.Run(tc.name, func(t *testing.T) {
            req := httptest.NewRequest("POST", "/api/orders", strings.NewReader(tc.body))
            req.Header.Set("Content-Type", "application/json")
            req.Header.Set("Authorization", "Bearer "+testJWT(t))

            res, err := app.Test(req, fiber.TestConfig{Timeout: 2 * time.Second})
            require.NoError(t, err)
            assert.Equal(t, tc.status, res.StatusCode)
        })
    }
}
```

### 6 — Verify

```
cd backend && go vet ./... && go test ./...
```

Any `vet` warning is a blocker. Any test failure is a blocker.

## Common Gotchas

- **Parse then validate** — never return from `BodyParser` failure without `validate.Struct`. A valid JSON with garbage field values passes `BodyParser` but fails `validate.Struct`.
- **Context propagation** — if you call a goroutine from a handler, derive its context from `c.UserContext()` AND handle cancellation, otherwise the client disconnecting leaks work.
- **Error envelope** — if you see raw `{"message": "..."}` in a response, someone skipped the central `ErrorHandler` registration. Check `fiber.Config{ErrorHandler: ...}` in `main.go`.
- **Handler → DB shortcut** — resist the urge. When you're tempted, add a service method. Handlers orchestrate; services decide.

## Verification

```
make lint-backend    # go vet + golangci-lint
make test-backend    # go test ./...
```

Both must pass before `cos task-done`.
