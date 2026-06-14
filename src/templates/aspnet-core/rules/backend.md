---
globs: ["src/backend/**/*.cs"]
alwaysApply: false
---

# ASP.NET Core Backend Rules (auto-loaded on src/backend/**/*.cs)

When editing any C# file under `src/backend/` in an ASP.NET Core project, follow these standards:

- **Endpoint signature** — minimal-API handlers take the DTO + injected services as parameters and return a typed value or `Results.*`. No response envelope built by hand.
- **Typed errors** — throw a typed exception (domain or `HttpException`-equivalent); a single `ExceptionHandlingMiddleware` maps it to the RFC 9457 problem shape `{type, title, status}`. Never write an error body anywhere else.
- **Cancellation** — flow `CancellationToken` from the endpoint into every downstream DB / HTTP call so cancellation propagates.
- **Validation** — validate request DTOs (DataAnnotations or FluentValidation); reject fail-closed with field-level details. No raw model binding without validation reaching a service.
- **Middleware order** — exception handling → routing → cors → auth → endpoints. Never put business logic in middleware.
- **Tests** — every endpoint gets `WebApplicationFactory<Program>` coverage, happy + error paths; services get host-free unit tests.
- **Separation** — Features/, Services, Repositories, Data/. Endpoints don't talk to the `DbContext` directly — services / repositories do.

Canonical policy: `docs/engineering/aspnet-core-rules.md`
Playbook: `docs/playbooks/aspnet-core-service.md`
Primary skill: `aspnet-core`
