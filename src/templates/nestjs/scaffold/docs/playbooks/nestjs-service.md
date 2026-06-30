<!-- domain:BACKEND | layer:playbook | ssot:true | updated:{{DATE}} -->
# NestJS Service Playbook

Purpose: The end-to-end recipe for adding or changing a NestJS endpoint in {{PROJECT_NAME}}.
Read when: Any task that adds a controller, provider, module, guard, pipe, or DTO.
Skip when: Pure infra/devops work — see the deployment docs.
Read next: [NestJS Engineering Rules](../engineering/nestjs-rules.md), [Error Format](../api-contracts/error-format.md)

> Nav: [Master Index](../00-index.md)

## Add an endpoint (the only sanctioned path)

1. **Contract first** — define the request/response DTOs (class-validator);
   error cases use the shared error envelope ([error-format](../api-contracts/error-format.md)).
2. **Module** — `src/backend/src/<feature>/<feature>.module.ts` declares the
   controller + providers and exports only what other modules need.
3. **Controller** — `<feature>.controller.ts`: validate via DTO + pipe, call
   exactly one provider method, return the value. No response envelope by hand.
4. **Provider** — `<feature>.service.ts`: business logic only, no `@Req`/`@Res`
   and no HTTP decorators, typed domain errors on failure.
5. **Repository** — data access for one aggregate; providers never touch the
   DB client directly.
6. **Wire** — import the feature module in `app.module.ts`.
7. **Test** — unit-test the provider via `Test.createTestingModule` (no HTTP) +
   supertest the controller via the `createApp()` factory (happy + error path).
8. **Verify** — `cd src/backend && npm run lint && npm test`.

## Global wiring (set once in `main.ts`)

`ValidationPipe (whitelist + transform) → global AllExceptionsFilter`. Both are
registered globally so every route inherits validation and one error shape.

## Anti-patterns

- Error JSON built inside a controller — the global filter owns the shape.
- A provider importing `@Req`/`@Res` — that layer must stay transport-free.
- `new SomeService()` instead of constructor injection — bypasses DI and breaks
  test overrides.
- Binding a real port in tests — always build through `createApp()`.
