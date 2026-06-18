---
name: node-express
tier: stack
domain: [backend]
description: Use when creating or modifying TypeScript files under src/backend/ in an Express service — routers, middleware, services, repositories, and their tests. Triggers on any .ts change under src/backend/. Covers router organization, middleware ordering, the central error handler, async handler wrapping, and request validation. Node.js fundamentals live in the core node-backend skill.
globs: "src/backend/**/*.ts"
depends_on:
  - clean-code
  - backend-fundamentals
  - node-backend
last_reviewed: "2026-06-11"
---

REQUIRED BACKGROUND: You MUST also follow the core `node-backend` skill (Node runtime, event loop, packaging) and `clean-code`. This skill adds Express-specific patterns on top.

# node-express

## Layer contract (matches `structure.tree`)

| Layer | May import | Never |
|---|---|---|
| `routes/` | services, middleware | repositories, other routers |
| `middleware/` | services (auth lookups) | repositories |
| `services/` | repositories, other services | express types (`Request`/`Response`) |
| `repositories/` | the DB client | services, express |

Services stay framework-free — that is what makes them unit-testable and what
keeps a future framework swap (Fastify, Hono) a routes-layer-only change.

## Router organization

- One router file per resource (`routes/users.ts` exports `usersRouter`).
- Handlers are thin: parse/validate → call ONE service method → shape response.
- Mount order in `index.ts`: body parsers → request-id/logging → auth →
  routers → 404 → **error handler last** (Express dispatches by registration
  order; a handler registered after the error middleware is unreachable).

## Async handlers

Express 4 does not catch rejected promises. Every async handler goes through
the wrap helper so rejections reach the central error handler instead of
crashing the process:

```ts
export const asyncHandler =
  (fn: RequestHandler): RequestHandler =>
  (req, res, next) => Promise.resolve(fn(req, res, next)).catch(next);
```

## Error handling

- ONE central error middleware shapes every error response (RFC 9457 problem
  shape per `docs/api-contracts/error-format.md`). Routes never build error
  JSON ad-hoc.
- Typed domain errors (`NotFoundError`, `ValidationError`) map to statuses in
  that one place; unknown errors → 500 with a generic message, full detail to
  the logger only (no stack traces to clients).

## Validation

Validate at the boundary (router) with a schema (zod or similar), reject
fail-closed, and hand the service a TYPED value — services never read `req`.

## Testing

- Services: pure unit tests, no HTTP.
- Routes: supertest against the app factory, one happy + one error-path test
  per endpoint minimum.
- The app is built by an exported `createApp()` factory so tests never bind a
  real port.
