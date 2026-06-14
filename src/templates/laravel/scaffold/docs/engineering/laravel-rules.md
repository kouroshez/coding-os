<!-- domain:BACKEND | layer:rules | ssot:true | updated:{{DATE}} -->
# Laravel Engineering Rules

Purpose: Non-negotiable conventions for the {{PROJECT_NAME}} Laravel backend.
Read when: Editing anything under `src/backend/`.
Skip when: Frontend/mobile work.
Read next: [Laravel Service Playbook](../playbooks/laravel-service.md)

> Nav: [Master Index](../00-index.md)

## Hard rules

1. **Layering** — controller → service → model, imports flow one way only.
2. **One error shaper** — only `app/Exceptions/Handler.php` writes error bodies;
   it logs full detail and returns the problem shape with no internals.
3. **Validation fail-closed** — every input goes through a Form Request; raw
   `$request->all()` never reaches a service.
4. **Mass-assignment safety** — `$fillable`/`$guarded` set on every model; never
   pass unvetted input to `Model::create()`.
5. **No N+1** — eager-load relations (`with()`); a query in a loop is a review
   finding.
6. **No floating config** — read config via `config()`/typed config objects,
   never `env()` outside `config/`.

## Testing bar

Services ≥ unit-tested per public method; routes ≥ happy + error path via feature
tests; database tests run against a disposable sqlite/in-memory connection.
