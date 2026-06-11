<!-- domain:BACKEND | layer:playbook | ssot:true | updated:2026-01-01 -->
# Express Service Playbook

Purpose: The end-to-end recipe for adding or changing an Express endpoint in cos-golden-fixture.
Read when: Any task that adds a route, middleware, service method, or repository.
Skip when: Pure infra/devops work — see the deployment docs.
Read next: [Express Engineering Rules](../engineering/express-rules.md), [Error Format](../api-contracts/error-format.md)

> Nav: [Master Index](../00-index.md)

## Add an endpoint (the only sanctioned path)

1. **Contract first** — define request/response shapes; error cases use the
   shared problem format ([error-format](../api-contracts/error-format.md)).
2. **Route** — `src/backend/src/routes/<resource>.ts`: validate input at the
   boundary, call exactly one service method, map the result to a response.
   Async handlers go through the `asyncHandler` wrapper.
3. **Service** — `src/services/<resource>-service.ts`: business logic only,
   no `Request`/`Response` types, typed domain errors on failure.
4. **Repository** — data access for one aggregate; services never touch the
   DB client directly.
5. **Wire** — mount the router in `src/index.ts` BEFORE the error handler.
6. **Test** — unit-test the service (no HTTP) + supertest the route via
   `createApp()` (one happy path, one error path, minimum).
7. **Verify** — `cd src/backend && npm run lint && npm test`.

## Middleware order (registration = dispatch order)

`json body parser → request-id/logging → auth → routers → 404 → error handler (last)`

## Anti-patterns

- Error JSON built inside a route — the central handler owns the shape.
- A service importing express types — that layer must stay framework-free.
- `app.listen` inside tests — always test through the `createApp()` factory.
