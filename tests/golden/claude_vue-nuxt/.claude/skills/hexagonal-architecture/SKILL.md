---
name: hexagonal-architecture
description: Design and refactor systems using Ports & Adapters (Hexagonal Architecture). Use when starting a new service, untangling framework-coupled business logic, supporting multiple delivery mechanisms (HTTP + queue + CLI), swapping infrastructure (Postgres → Mongo, REST → gRPC) without touching domain code, or planning long-lived enterprise systems where framework churn is a real risk. Covers Go+Fiber, Python+FastAPI, and React Native client adaptations.
tier: cross-cutting
domain: [architecture]
last_reviewed: "2026-05-11"

---

# Hexagonal Architecture — Ports & Adapters

A practical playbook for building business-logic-first systems where the domain is shielded from frameworks, transports, and persistence. Pattern by Alistair Cockburn (2005); proven across two decades of Java, .NET, Go, Python, and TypeScript codebases.

## When to Use This Skill

Invoke this skill **before** writing the first business-logic file in a new service, **or** when you find yourself:

- Writing tests that mock five frameworks just to assert one business rule
- Wanting to add a CLI / cron / queue-consumer entry point but every code path threads through HTTP request/response objects
- Replacing PostgreSQL with another store and discovering business code imports `sqlalchemy` directly
- Asking "where does the *real* logic live?" and finding the answer is "scattered across controllers"
- Planning a long-lived system where the current framework will be obsolete in 5 years

**Skip** for: throwaway scripts, one-off scrapers, CRUD-only admin tools where the framework IS the application.

## The Three Layers

```
┌─────────────────────────────────────────────────────────────┐
│  ADAPTERS (infrastructure + delivery)                       │
│   ┌─────────────┐    ┌─────────────┐    ┌──────────────┐   │
│   │ HTTP route  │    │ CLI command │    │ Queue worker │   │  ← inbound
│   └──────┬──────┘    └──────┬──────┘    └──────┬───────┘   │
│          │                  │                   │           │
│          ▼                  ▼                   ▼           │
│  ╔══════════════════════════════════════════════════════╗   │
│  ║  APPLICATION (use cases — orchestrate domain)        ║   │
│  ║                                                      ║   │
│  ║  ╔══════════════════════════════════════════════╗    ║   │
│  ║  ║  DOMAIN (entities, value objects, rules)     ║    ║   │
│  ║  ║                                              ║    ║   │
│  ║  ║  Pure. No framework imports. No I/O.         ║    ║   │
│  ║  ╚══════════════════════════════════════════════╝    ║   │
│  ║                                                      ║   │
│  ║  Outbound port interfaces live here.                 ║   │
│  ╚════════════════════════════════════════════════╤═════╝   │
│          ▲                  ▲                     ▲          │
│          │                  │                     │          │  ← outbound
│   ┌──────┴──────┐    ┌──────┴──────┐    ┌────────┴───────┐  │
│   │ Postgres    │    │ Redis cache │    │ Stripe SDK     │  │
│   │ repository  │    │ adapter     │    │ adapter        │  │
│   └─────────────┘    └─────────────┘    └────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### 1. Domain (innermost, framework-free)

The "what is true about the business" layer. Entities (have identity over time), value objects (immutable, identity-by-value), and domain services (operations that don't naturally belong to one entity).

**Rules:**

- ZERO framework imports. No `gorm`, `sqlalchemy`, `fiber`, `fastapi`, `react`. Standard library only.
- No I/O. No `time.Now()` / `datetime.now()` directly — inject a `Clock` port.
- No randomness. Inject a `UUIDGen` / `RandomSource` port if needed.
- Domain types raise domain-level exceptions (`InsufficientBalance`, not `HTTPException(400)`).

### 2. Application (use cases)

Orchestrates the domain. One use case = one user-meaningful operation (`PlaceOrder`, `RegisterUser`, `RecommendNextLesson`).

**Each use case:**

- Has a single public method (typically named `execute`, `handle`, or `__call__`)
- Receives a typed input (Command / Query DTO) — never an HTTP request object
- Returns a typed output — never an HTTP response object
- Depends only on **outbound port interfaces** (repositories, gateways, clock) — never concrete implementations
- Wraps domain operations in a transaction when needed (via a `UnitOfWork` outbound port)

### 3. Adapters (outermost, framework-coupled)

Two flavors:

- **Inbound (driving)** — turn external triggers into use case invocations. HTTP route → parse body → build Command → call `usecase.execute(command)` → format response.
- **Outbound (driven)** — implement outbound port interfaces using infrastructure. PostgresUserRepository, StripeBillingGateway, RedisRateLimiter, SystemClock.

The **composition root** is the only place where concrete adapters are wired to use cases — typically `main.go` / `main.py` / `app.tsx`.

## Ports — the Contracts

A port is an interface. Two kinds:

| Kind | Where it lives | Purpose | Examples |
|---|---|---|---|
| **Inbound port** | Application layer | What the app *can do* | `PlaceOrder`, `GetUserProfile` (use case interfaces) |
| **Outbound port** | Application layer (or domain if truly domain-level) | What the app *needs* | `UserRepository`, `PaymentGateway`, `Clock`, `UUIDGen`, `EmailSender` |

**Critical**: outbound port interfaces are owned by the **application layer**, not by the adapter that implements them. This is dependency inversion — the consumer defines the contract, the implementer adapts.

```
✗ WRONG: postgres/repository.go defines UserRepo, app/usecase.go imports it
✓ RIGHT: app/ports/user_repository.go defines UserRepository,
         postgres/user_repository.go implements it
```

## Per-Stack Layouts

This project spans Go+Fiber (business core), Python+FastAPI (AI adapter service), and React Native (mobile client). The hexagonal pattern translates differently to each idiom — see the dedicated references:

- **Go+Fiber backend** — see [references/go-fiber-layout.md](references/go-fiber-layout.md) — folder layout, interface conventions, wire-style composition root, `internal/` boundary enforcement.
- **Python+FastAPI service** — see [references/python-fastapi-layout.md](references/python-fastapi-layout.md) — protocol-based ports, dependency injection via `Depends`, async use cases, Pydantic at boundaries only.
- **React Native client** — see [references/react-native-layout.md](references/react-native-layout.md) — domain in TypeScript, screens-as-adapters, hooks as composition root, why this still pays off on mobile.
- **Anti-patterns** — see [references/anti-patterns.md](references/anti-patterns.md) — anemic domain, leaky framework types in ports, port-as-DTO confusion, premature port extraction.

## Decision Points

When applying this skill, walk through these in order:

### 1. Is this a new service or a refactor?

- **New service**: scaffold the three folders before writing the first line of business logic. Use [assets/folder-scaffold.md](assets/folder-scaffold.md).
- **Refactor**: identify the existing god-class / fat controller. Extract domain types first, then use cases, then port interfaces. Adapters come last.

### 2. What are the inbound surfaces?

List every way the use case is triggered: HTTP route, CLI command, scheduled job, queue consumer, gRPC method, GraphQL resolver. Each becomes an inbound adapter. The use case itself does not change.

### 3. What does the use case need?

List every external dependency: data store, external API, email/SMS, message bus, secret store, clock, randomness. Each becomes an outbound port.

### 4. Where do DTOs live?

- **Command/Query DTOs** at use case boundary — application layer.
- **HTTP request/response DTOs** — inbound adapter (REST controller).
- **Database row structs** — outbound adapter (repository).
- **Domain entities** — domain layer.

DTOs cross **only one** layer boundary. The HTTP request struct is parsed in the controller into a Command DTO that the use case understands. The use case returns a result DTO that the controller maps to an HTTP response. **Never let an `HttpRequest` reach the use case.**

### 5. Where does the transaction live?

Outbound port `UnitOfWork` (or `Transactor`). Use case receives it and calls `uow.run(lambda: ...)`. The Postgres adapter implements it with `BEGIN/COMMIT`. The in-memory test adapter implements it with a no-op. **Never sprinkle `BEGIN/COMMIT` in repositories.**

## Testing Strategy

Hexagonal pays its biggest dividend in tests:

- **Domain tests** — pure unit tests, no mocks. `OrderTotal_when_two_items_returns_sum`.
- **Use case tests** — wire fake (in-memory) outbound adapters, drive the use case, assert outputs and adapter side-effects. Fast, deterministic, covers business rules.
- **Adapter tests** — integration tests against real infrastructure (real Postgres in a Docker container, real Stripe sandbox). Slow but few.
- **End-to-end tests** — full HTTP-to-DB. Smoke level only; the use case tests already cover branches.

Inverted from the usual pyramid: lots of fast use-case tests, very few e2e tests.

```
        /\
       /  \   e2e (5%)
      /────\
     / adapt\  adapter integration (15%)
    /────────\
   /          \  use case + domain (80%)
  /────────────\
```

## Common Pitfalls (full list in references/anti-patterns.md)

1. **Anemic domain** — entities are bags of public fields with no behavior. The "domain" is just data classes; rules live in services. Symptom: every "domain" file is a struct/dataclass with zero methods.
2. **Framework types in ports** — outbound port returns `*sql.Rows` or `dict[str, Any]`. The adapter is supposed to hide the framework, not leak it.
3. **God use case** — one `OrderService` with 20 public methods. Each method should be its own use case class.
4. **Premature port extraction** — every concrete class wrapped in an interface "just in case". Only extract a port when you have a real reason: testability, two implementations, or anticipated swap.
5. **Reverse dependency** — domain imports from application or adapters. The dependency rule says inner layers know nothing of outer. If you need infrastructure at domain level, you're missing a port.

## Composition Root

Every entrypoint (main, server bootstrap, lambda handler) wires the graph **once**:

```
main()
 ├─ load config
 ├─ build outbound adapters (PostgresUserRepo, StripeGateway, SystemClock)
 ├─ build use cases (PlaceOrder(repo, gateway, clock))
 ├─ build inbound adapters (HTTPRouter(placeOrderUseCase))
 └─ start server
```

For Go: hand-wired or use `google/wire`. For Python: hand-wired or `dependency-injector`. For TypeScript: hand-wired (avoid InversifyJS unless team is large).

## Source Material

The patterns in this skill draw from:

- Alistair Cockburn — original Hexagonal Architecture article (2005)
- "Cosmic Python" (Percival & Gregory) — for Python idioms
- Kat Zien — "How Do You Structure Your Go Apps?" (GopherCon talk)
- Robert C. Martin — "Clean Architecture" (the layered cousin)
- Vaughn Vernon — "Implementing Domain-Driven Design" (chapter on hexagonal)
- "Get Your Hands Dirty on Clean Architecture" (Tom Hombergs) — concrete Java patterns

Per-stack adaptation references in this skill point to the current 2026 community guidance for Go modules layout, FastAPI dependency injection, and React Native source organization.
