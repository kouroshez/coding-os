---
globs: ["src/backend/**/*.php"]
alwaysApply: false
---

# Laravel Backend Rules (auto-loaded on src/backend/**/*.php)

When editing any PHP file under `src/backend/` in a Laravel project, follow these standards:

- **Layering** — controller → service → model; imports flow one way only. Controllers stay thin; business logic lives in services, persistence in Eloquent models.
- **One error shaper** — only `app/Exceptions/Handler.php` writes error bodies; it logs full detail and returns the problem shape with no internals (no SQL, no stack traces).
- **Validation fail-closed** — every input goes through a Form Request; raw `$request->all()` never reaches a service.
- **Mass-assignment safety** — set `$fillable`/`$guarded` on every model; never pass unvetted input to `Model::create()`.
- **No N+1** — eager-load relations with `with()`; a query inside a loop is a review finding.
- **No floating config** — read config via `config()` / typed config objects, never `env()` outside `config/`.
- **Testing bar** — services unit-tested per public method; routes covered happy + error path via feature tests against a disposable sqlite connection.

Canonical policy: `docs/engineering/laravel-rules.md`
Playbook: `docs/playbooks/laravel-service.md`
Primary skill: `laravel`
