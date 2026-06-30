---
name: nestjs
tier: stack
domain: [backend]
description: Use when creating or modifying TypeScript files under src/backend/ in a NestJS service — modules, controllers, providers (services), guards, pipes, interceptors, DTOs, and their tests. Triggers on any .ts change under src/backend/. Covers module/DI wiring, thin controllers, the global exception filter, the global ValidationPipe + class-validator DTOs, and provider testing with the Nest testing module. Node.js fundamentals live in the core node-backend skill.
globs: "src/backend/**/*.ts"
depends_on:
  - clean-code
  - backend-fundamentals
  - node-backend
last_reviewed: "2026-06-14"
---

REQUIRED BACKGROUND: You MUST also follow the core `node-backend` skill (Node runtime, event loop, packaging) and `clean-code`. This skill adds NestJS-specific patterns on top.

# nestjs

## Layer contract (matches `structure.tree`)

| Layer | May import | Never |
|---|---|---|
| `*.controller.ts` | the feature provider, DTOs | repositories, other controllers |
| `*.service.ts` (provider) | repositories, other providers | `@Req`/`@Res`, HTTP decorators |
| `repositories/` | the DB client | providers, controllers |
| `common/` (filters/pipes/guards) | providers (for auth lookups) | repositories |

Providers stay transport-free — no `@Req()`/`@Res()` — so they are
unit-testable and a transport swap (REST → GraphQL → microservice) is a
controller-layer-only change.

## Modules & DI

- One feature = one module (`UsersModule`) declaring its controller + providers;
  export only what other modules need.
- The root `AppModule` wires feature modules — it owns no business logic.
- Inject by constructor with `private readonly`; never `new` a provider — that
  bypasses the DI container and breaks testing/overrides.
- Configurable modules use `forRoot()`/`forFeature()`; never read `process.env`
  deep in a provider — surface config through a typed `ConfigService`.

## Controllers (thin)

- Handlers parse/validate (DTO + pipe) → call ONE provider method → return the
  value. Nest serializes; do not build the response envelope by hand.
- No try/catch for error shaping in a controller — throw a typed `HttpException`
  (or a domain error mapped by the filter) and let the global filter shape it.

## Validation

- A global `ValidationPipe({ whitelist: true, forbidNonWhitelisted: true,
  transform: true })` in `main.ts`. Every body/param is a class-validator DTO;
  reject fail-closed; the provider receives a typed, validated value and never
  reads the raw request.

## Error handling

- ONE global exception filter (`common/all-exceptions.filter.ts`) shapes every
  error response (the canonical envelope per `docs/api-contracts/error-format.md`).
  Unknown errors → 500 generic message, full detail to the logger only.

## Testing

- Providers: pure unit tests via `Test.createTestingModule({...}).compile()`,
  override dependencies with mocks — no HTTP.
- Controllers/e2e: `supertest` against the app built by the `createApp()`
  factory, one happy + one error-path per endpoint minimum.
- Never bind a real port in tests; build through the Nest testing module.
