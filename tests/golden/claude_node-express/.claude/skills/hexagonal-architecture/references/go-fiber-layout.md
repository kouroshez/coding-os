# Hexagonal Layout — Go + Fiber Backend

The canonical Go module layout that keeps Fiber out of the domain. Tested in production for services 5k–50k LOC. Bigger than that, split into bounded contexts (each with its own hexagon).

## Folder Tree

```
backend/
├── cmd/
│   └── api/
│       └── main.go                ← composition root: wires adapters → use cases → router
├── internal/                       ← Go's compiler-enforced privacy boundary
│   ├── domain/                    ← INNER LAYER — pure, no framework imports
│   │   ├── user/
│   │   │   ├── user.go            ← entity: NewUser, ChangeEmail, etc.
│   │   │   ├── email.go           ← value object with parse + validation
│   │   │   ├── errors.go          ← ErrEmailTaken, ErrInactive (domain errors)
│   │   │   └── user_test.go
│   │   └── order/
│   │       ├── order.go           ← entity with state machine: pending → paid → shipped
│   │       ├── line_item.go       ← value object
│   │       └── order_test.go
│   │
│   ├── app/                        ← APPLICATION LAYER — use cases + ports
│   │   ├── ports/                 ← outbound port interfaces (driven side)
│   │   │   ├── user_repository.go ← UserRepository interface
│   │   │   ├── order_repository.go
│   │   │   ├── payment_gateway.go
│   │   │   ├── clock.go           ← Clock interface (Now() time.Time)
│   │   │   ├── uuid_gen.go
│   │   │   └── unit_of_work.go    ← Transactor for atomic multi-repo ops
│   │   │
│   │   └── usecase/               ← one file per use case
│   │       ├── place_order.go
│   │       ├── place_order_test.go ← uses fake adapters from app/fakes/
│   │       ├── register_user.go
│   │       └── cancel_order.go
│   │
│   └── adapter/                    ← OUTER LAYER — framework-coupled
│       ├── http/                  ← INBOUND adapter — Fiber route handlers
│       │   ├── server.go          ← *fiber.App build + middleware chain
│       │   ├── order_handler.go   ← parses HTTP → calls usecase → renders JSON
│       │   ├── user_handler.go
│       │   └── middleware/
│       │       ├── auth.go
│       │       └── rate_limit.go
│       │
│       ├── postgres/               ← OUTBOUND adapter — pgx-based repos
│       │   ├── pool.go            ← *pgxpool.Pool builder (DI'd from main)
│       │   ├── user_repository.go ← implements ports.UserRepository
│       │   ├── order_repository.go
│       │   ├── unit_of_work.go    ← BEGIN/COMMIT wrapper
│       │   └── migrations/
│       │       └── 001_init.sql
│       │
│       ├── stripe/                 ← OUTBOUND adapter — Stripe SDK wrapper
│       │   └── payment_gateway.go ← implements ports.PaymentGateway
│       │
│       ├── system/                 ← OUTBOUND adapters — system primitives
│       │   ├── clock.go           ← time.Now() impl of ports.Clock
│       │   └── uuid_gen.go        ← google/uuid impl
│       │
│       └── fakes/                  ← in-memory adapters used by use case tests
│           ├── user_repository.go
│           ├── order_repository.go
│           ├── payment_gateway.go
│           └── clock.go           ← FrozenClock for deterministic tests
│
├── pkg/                            ← code that DOES expose to other modules
│   └── apperr/                    ← error envelope shared with HTTP responses
│       └── apperr.go
│
└── go.mod
```

## Why `internal/`?

Everything under `internal/` is invisible to other Go modules — the compiler enforces this. It is the strongest "private" boundary Go offers. Use it ruthlessly: only `cmd/` and `pkg/` are public.

`pkg/` should be tiny — only types deliberately shared (error codes that clients reference, telemetry constants).

## Port Definition Convention

Outbound ports live in `internal/app/ports/`, **NOT** in the adapter packages.

```go
// internal/app/ports/user_repository.go — owned by application layer
package ports

import (
    "context"

    "myapp/internal/domain/user"
)

type UserRepository interface {
    Save(ctx context.Context, u *user.User) error
    FindByID(ctx context.Context, id user.ID) (*user.User, error)
    FindByEmail(ctx context.Context, email user.Email) (*user.User, error)
}
```

```go
// internal/adapter/postgres/user_repository.go — implements the port
package postgres

import (
    "context"

    "github.com/jackc/pgx/v5/pgxpool"
    "myapp/internal/app/ports"
    "myapp/internal/domain/user"
)

type UserRepository struct {
    pool *pgxpool.Pool
}

// Compile-time check that we satisfy the port. If the port grows a method,
// this line breaks the build at the adapter — exactly where the fix belongs.
var _ ports.UserRepository = (*UserRepository)(nil)

func NewUserRepository(pool *pgxpool.Pool) *UserRepository {
    return &UserRepository{pool: pool}
}

func (r *UserRepository) Save(ctx context.Context, u *user.User) error {
    _, err := r.pool.Exec(ctx, `
        INSERT INTO users (id, email, created_at)
        VALUES ($1, $2, $3)
        ON CONFLICT (id) DO UPDATE SET email = $2
    `, u.ID, u.Email.String(), u.CreatedAt)
    return err
}
```

## Use Case Skeleton

```go
// internal/app/usecase/place_order.go
package usecase

import (
    "context"
    "errors"

    "myapp/internal/app/ports"
    "myapp/internal/domain/order"
    "myapp/internal/domain/user"
)

// PlaceOrderInput is the command DTO. Field types are domain types or
// primitives — never *fiber.Ctx, never anything HTTP-aware.
type PlaceOrderInput struct {
    UserID  user.ID
    Items   []order.LineItem
    Promo   string // optional
}

type PlaceOrderOutput struct {
    OrderID order.ID
    Total   order.Money
}

type PlaceOrder struct {
    users    ports.UserRepository
    orders   ports.OrderRepository
    payments ports.PaymentGateway
    uow      ports.UnitOfWork
    clock    ports.Clock
    uuid     ports.UUIDGen
}

func NewPlaceOrder(
    users ports.UserRepository,
    orders ports.OrderRepository,
    payments ports.PaymentGateway,
    uow ports.UnitOfWork,
    clock ports.Clock,
    uuid ports.UUIDGen,
) *PlaceOrder {
    return &PlaceOrder{users, orders, payments, uow, clock, uuid}
}

func (uc *PlaceOrder) Execute(ctx context.Context, in PlaceOrderInput) (*PlaceOrderOutput, error) {
    u, err := uc.users.FindByID(ctx, in.UserID)
    if err != nil {
        return nil, err
    }
    if !u.Active() {
        return nil, user.ErrInactive
    }

    o, err := order.New(uc.uuid.New(), u.ID, in.Items, uc.clock.Now())
    if err != nil {
        return nil, err
    }

    var charge ports.PaymentResult
    err = uc.uow.Run(ctx, func(ctx context.Context) error {
        if err := uc.orders.Save(ctx, o); err != nil {
            return err
        }
        charge, err = uc.payments.Charge(ctx, ports.ChargeRequest{
            OrderID: o.ID, Amount: o.Total(),
        })
        if err != nil {
            return err
        }
        o.MarkPaid(charge.TransactionID, uc.clock.Now())
        return uc.orders.Save(ctx, o)
    })
    if err != nil {
        return nil, err
    }

    return &PlaceOrderOutput{OrderID: o.ID, Total: o.Total()}, nil
}
```

## Inbound Adapter — Fiber Handler

The handler does **only**: parse HTTP → build Command → call use case → format response. No business logic.

```go
// internal/adapter/http/order_handler.go
package http

import (
    "github.com/gofiber/fiber/v3"
    "myapp/internal/app/usecase"
    "myapp/internal/domain/order"
    "myapp/internal/domain/user"
    "myapp/pkg/apperr"
)

type OrderHandler struct {
    placeOrder *usecase.PlaceOrder
}

func NewOrderHandler(placeOrder *usecase.PlaceOrder) *OrderHandler {
    return &OrderHandler{placeOrder: placeOrder}
}

// HTTP-shape DTO — lives in the adapter, never crosses inward.
type placeOrderRequest struct {
    UserID string                  `json:"user_id"`
    Items  []placeOrderLineItem   `json:"items"`
    Promo  string                  `json:"promo,omitempty"`
}

type placeOrderLineItem struct {
    SKU      string `json:"sku"`
    Quantity int    `json:"quantity"`
}

func (h *OrderHandler) PlaceOrder(c fiber.Ctx) error {
    var req placeOrderRequest
    if err := c.Bind().JSON(&req); err != nil {
        return apperr.BadRequest(c, "invalid_payload", err)
    }

    // Translate primitives → domain value objects at the boundary.
    userID, err := user.ParseID(req.UserID)
    if err != nil {
        return apperr.BadRequest(c, "invalid_user_id", err)
    }
    items := make([]order.LineItem, 0, len(req.Items))
    for _, it := range req.Items {
        sku, err := order.ParseSKU(it.SKU)
        if err != nil {
            return apperr.BadRequest(c, "invalid_sku", err)
        }
        items = append(items, order.LineItem{SKU: sku, Quantity: it.Quantity})
    }

    out, err := h.placeOrder.Execute(c.Context(), usecase.PlaceOrderInput{
        UserID: userID, Items: items, Promo: req.Promo,
    })
    if err != nil {
        return apperr.FromDomainError(c, err)
    }

    return c.JSON(fiber.Map{
        "order_id": out.OrderID.String(),
        "total":    out.Total.String(),
    })
}
```

## Composition Root — `cmd/api/main.go`

```go
package main

import (
    "context"
    "log"
    "os/signal"
    "syscall"

    "github.com/gofiber/fiber/v3"
    "github.com/jackc/pgx/v5/pgxpool"
    "myapp/internal/adapter/http"
    "myapp/internal/adapter/postgres"
    "myapp/internal/adapter/stripe"
    "myapp/internal/adapter/system"
    "myapp/internal/app/usecase"
)

func main() {
    ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
    defer stop()

    cfg := loadConfig()

    // ── Outbound adapters
    pool, err := pgxpool.New(ctx, cfg.DatabaseURL)
    if err != nil {
        log.Fatalf("pg pool: %v", err)
    }
    defer pool.Close()

    users    := postgres.NewUserRepository(pool)
    orders   := postgres.NewOrderRepository(pool)
    payments := stripe.NewPaymentGateway(cfg.StripeKey)
    uow      := postgres.NewUnitOfWork(pool)
    clock    := system.NewClock()
    uuid     := system.NewUUIDGen()

    // ── Use cases
    placeOrder := usecase.NewPlaceOrder(users, orders, payments, uow, clock, uuid)
    cancelOrder := usecase.NewCancelOrder(orders, payments, clock)

    // ── Inbound adapter
    app := fiber.New(fiber.Config{ErrorHandler: http.GlobalErrorHandler})
    http.Mount(app, http.Handlers{
        Order: http.NewOrderHandler(placeOrder),
        // ... other handlers
    })

    go func() { _ = app.Listen(":" + cfg.Port) }()
    <-ctx.Done()
    _ = app.ShutdownWithTimeout(cfg.ShutdownTimeout)
}
```

## Use Case Tests — Fast, No Docker

```go
// internal/app/usecase/place_order_test.go
package usecase_test

import (
    "context"
    "testing"
    "time"

    "github.com/stretchr/testify/assert"
    "github.com/stretchr/testify/require"
    "myapp/internal/adapter/fakes"
    "myapp/internal/app/usecase"
    "myapp/internal/domain/order"
    "myapp/internal/domain/user"
)

func TestPlaceOrder_succeeds_for_active_user(t *testing.T) {
    ctx := context.Background()

    users := fakes.NewUserRepository()
    orders := fakes.NewOrderRepository()
    payments := fakes.NewPaymentGateway()
    uow := fakes.NewUnitOfWork()
    clock := fakes.NewFrozenClock(time.Date(2026, 4, 26, 12, 0, 0, 0, time.UTC))
    uuid := fakes.NewSequentialUUIDGen()

    u := user.MustNew(user.MustParseID("usr_1"), user.MustParseEmail("a@b.com"))
    require.NoError(t, users.Save(ctx, u))

    uc := usecase.NewPlaceOrder(users, orders, payments, uow, clock, uuid)

    out, err := uc.Execute(ctx, usecase.PlaceOrderInput{
        UserID: u.ID,
        Items:  []order.LineItem{{SKU: order.MustParseSKU("BOOK-1"), Quantity: 2}},
    })

    require.NoError(t, err)
    assert.Equal(t, "ord_1", out.OrderID.String())
    assert.Equal(t, 1, payments.ChargeCallCount())
    saved, _ := orders.FindByID(ctx, out.OrderID)
    assert.True(t, saved.IsPaid())
}
```

No Docker. No Fiber. No pgx. Runs in milliseconds. Covers the actual business logic.

## Lint Rules to Enforce This

A repo-level `go vet` check (or `golangci-lint` config) that bans imports across layer boundaries:

```yaml
# .golangci.yml — depguard rule
linters-settings:
  depguard:
    rules:
      domain-pure:
        files: ["**/internal/domain/**"]
        deny:
          - pkg: "github.com/gofiber/**"
            desc: "domain must not import http frameworks"
          - pkg: "github.com/jackc/pgx/**"
            desc: "domain must not import database drivers"
          - pkg: "github.com/stripe/**"
            desc: "domain must not import vendor SDKs"
      app-from-domain-only:
        files: ["**/internal/app/**"]
        deny:
          - pkg: "github.com/gofiber/**"
          - pkg: "github.com/jackc/pgx/**"
```

This catches the most common drift: someone reaches for `*fiber.Ctx` inside a use case "just for this one case".

## Key References

- Kat Zien — *How Do You Structure Your Go Apps?* (GopherCon 2018, still the canonical talk).
- Ben Johnson — *Standard Package Layout* (post-2017, holds up).
- `internal/` privacy: <https://go.dev/doc/go1.4#internalpackages>
- Fiber v3 docs (Bind, ErrorHandler, fiber.Ctx) at gofiber.io.
