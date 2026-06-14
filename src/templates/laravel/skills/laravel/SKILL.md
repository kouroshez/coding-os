---
name: laravel
tier: stack
domain: [backend]
description: Use when creating or modifying PHP files under src/backend/ in a Laravel application — routes, controllers, services, Eloquent models, Form Requests, middleware, and their tests. Triggers on any .php change under src/backend/. Covers thin controllers, the exception Handler as the single error shaper, Form Request validation, Eloquent N+1 avoidance, and mass-assignment safety. Core PHP conventions live in the php skill.
globs: "src/backend/**/*.php"
depends_on:
  - clean-code
  - backend-fundamentals
  - php
last_reviewed: "2026-06-14"
---

REQUIRED BACKGROUND: You MUST also follow the core `php` skill (language idioms, typing, Composer) and `clean-code`. This skill adds Laravel-specific patterns on top.

# laravel

## Layer contract (matches `structure.tree`)

| Layer | May import | Never |
|---|---|---|
| `Http/Controllers/` | services, Form Requests | Eloquent queries, other controllers |
| `Services/` | models, other services | `Request`/`Response` |
| `Models/` | the query builder | services, controllers |
| `Exceptions/Handler.php` | — | building responses anywhere else |

Services stay framework-light so they are unit-testable and a delivery swap
(HTTP → queue job → console) is a controller-layer-only change.

## Controllers (thin)

- Type-hint a Form Request to validate; the controller receives validated data.
- Call ONE service method, return the value (Laravel serializes). No response
  envelope by hand, no try/catch for error shaping.

## Validation

- Every write endpoint has a Form Request; reject fail-closed. Raw
  `$request->all()` never crosses into a service.

## Eloquent

- `$fillable`/`$guarded` on every model (mass-assignment safety).
- Eager-load relations (`with()`); a query inside a loop is an N+1 finding.
- Queries live in models/services, never in controllers.

## Error handling

- ONE shaper: `app/Exceptions/Handler.php` returns the RFC 9457 problem shape
  (`docs/api-contracts/error-format.md`). 5xx logs full detail; the client never
  sees a stack trace.

## Testing

- Services: unit tests per public method. Routes: feature tests (happy + error).
- DB tests use a disposable sqlite/in-memory connection; never the dev database.
