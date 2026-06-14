<!-- domain:BACKEND | layer:playbook | ssot:true | updated:{{DATE}} -->
# ASP.NET Core Service Playbook

Purpose: The end-to-end recipe for adding or changing an ASP.NET Core endpoint in {{PROJECT_NAME}}.
Read when: Any task that adds an endpoint, controller, service, middleware, or DTO.
Skip when: Pure infra/devops work — see the deployment docs.
Read next: [ASP.NET Core Engineering Rules](../engineering/aspnet-core-rules.md), [Error Format](../api-contracts/error-format.md)

> Nav: [Master Index](../00-index.md)

## Add an endpoint (the only sanctioned path)

1. **Contract first** — define the request/response DTOs as records; error cases
   use the shared problem format ([error-format](../api-contracts/error-format.md)).
2. **Feature folder** — `src/backend/Features/<Feature>/` holds the endpoints +
   service for one domain; nothing else reaches into it.
3. **Endpoints** — `<Feature>Endpoints.cs`: bind/validate the DTO, call exactly
   one service method, return the value. No response envelope built by hand.
4. **Service** — `<Feature>Service.cs`: business logic only, no `HttpContext` and
   no transport types, typed domain exceptions on failure.
5. **Repository** — data access for one aggregate; services never touch the
   `DbContext` directly.
6. **Wire** — register the service in `Program.cs` and call `<Feature>Endpoints.Map(app)`.
7. **Test** — unit-test the service (no host) + `WebApplicationFactory<Program>`
   integration-test the endpoint (happy + error path).
8. **Verify** — `cd src/backend && dotnet format --verify-no-changes && dotnet test`.

## Global wiring (set once in `Program.cs`)

`builder.Services.Add*` registrations → `app.UseMiddleware<ExceptionHandlingMiddleware>()`
runs first so every downstream handler inherits one error shape.

## Anti-patterns

- Error JSON built inside an endpoint — the middleware owns the shape.
- A service importing `HttpContext`/`IHttpContextAccessor` — that layer must stay
  transport-free.
- `new SomeService()` instead of constructor / parameter injection — bypasses the
  container and breaks test overrides.
- Binding a real port in tests — always build through `WebApplicationFactory<Program>`.
