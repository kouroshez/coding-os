---
name: aspnet-core
tier: stack
domain: [backend]
description: Use when creating or modifying C# files under src/backend/ in an ASP.NET Core service — Program bootstrap, minimal-API endpoints or controllers, services, middleware, DI registrations, DTOs, and their tests. Triggers on any .cs change under src/backend/. Covers DI/container wiring, thin endpoints, the global exception-handling middleware, fail-closed DTO validation, the options pattern for config, and service testing with WebApplicationFactory. Also known as dotnet.
globs: "src/backend/**/*.cs"
depends_on:
  - clean-code
  - backend-fundamentals
  - api-design
last_reviewed: "2026-06-14"
---

REQUIRED BACKGROUND: You MUST also follow the core `clean-code` and
`backend-fundamentals` skills. This skill adds ASP.NET Core-specific patterns
on top.

# aspnet-core

## Layer contract (matches `structure.tree`)

| Layer | May import | Never |
|---|---|---|
| `*Endpoints.cs` / controllers | the feature service, DTOs | repositories, other endpoints |
| `*Service.cs` | repositories, other services | `HttpContext`, `IHttpContextAccessor`, transport types |
| `Repositories/` | the `DbContext` / DB client | services, endpoints |
| `Common/` (middleware/filters) | services (for auth lookups) | repositories |

Services stay transport-free — no `HttpContext` — so they are unit-testable and
a transport swap (minimal API → controllers → gRPC) is an endpoint-layer-only
change.

## DI & wiring

- Register every service in `Program.cs` (`AddScoped`/`AddSingleton`/`AddTransient`);
  resolve by constructor or endpoint-parameter injection — never `new` a service.
- `Program.cs` owns wiring only, not business logic. One `WebApplication`,
  middleware pipeline registered once, feature endpoints mapped via
  `<Feature>Endpoints.Map(app)`.
- Lifetimes: `Scoped` for per-request (the default for services touching the DB),
  `Singleton` only for stateless/thread-safe helpers, `Transient` for cheap
  stateless objects. A captive dependency (Singleton holding a Scoped) is a bug.
- Keep `Program` reachable to tests (`public partial class Program;`) so
  `WebApplicationFactory<Program>` can build the app without binding a port.

## Endpoints (thin)

- A handler binds/validates the DTO → calls ONE service method → returns the
  value (the host serializes). Do not build the response envelope by hand.
- No try/catch for error shaping in an endpoint — throw a typed exception and let
  the global middleware shape it.
- Flow `CancellationToken` from the handler into every downstream call.

## Validation

- Every body/route/query input is a validated DTO (DataAnnotations or
  FluentValidation); reject fail-closed before the service runs. The service
  receives a typed, validated value and never reads the raw request.

## Error handling

- ONE global `ExceptionHandlingMiddleware` (`Common/ExceptionHandlingMiddleware.cs`)
  shapes every error response (RFC 9457 problem shape per
  `docs/api-contracts/error-format.md`). Unknown exceptions → 500 generic
  message, full detail to the logger only — never a stack trace to the client.
- Register it first in the pipeline (`app.UseMiddleware<ExceptionHandlingMiddleware>()`)
  so it wraps all downstream handlers.

## Configuration

- Bind configuration once at bootstrap via the options pattern (`IOptions<T>`);
  services receive typed options and never read raw configuration keys deep in a
  method.

## Testing

- Services: pure unit tests, no host — construct with fakes/mocks and assert.
- Endpoints/integration: `WebApplicationFactory<Program>` builds the app
  in-memory; one happy + one error-path per endpoint minimum.
- Never bind a real port in tests; always build through the factory.
