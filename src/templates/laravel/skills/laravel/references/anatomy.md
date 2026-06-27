<!-- domain:LARAVEL | layer:reference | ssot:true | updated:2026-06-27 -->
# Laravel Anatomy

> P: Canonical file map + entity recipes for the Laravel (thin-controller, service-layer) stack.
> R: Adding any `.php` under `src/backend/`, or routing a backend task.
> S: Reading frontend / mobile code — wrong stack.
> N: [SKILL.md](../SKILL.md), [scaffold-boundary.yaml](../../../scaffold-boundary.yaml)

> Nav: [Skill](../SKILL.md)

---

## 1. Boundary

SSOT: `src/templates/laravel/scaffold-boundary.yaml`.

## 2. Layout map

| Pattern | Location | Naming | Imports from | Description |
|---|---|---|---|---|
| Controller | `app/Http/Controllers/<Name>Controller.php` | `<Name>Controller.php` | its service | Thin — validate, delegate, respond |
| Form Request | `app/Http/Requests/<Name>Request.php` | `<Name>Request.php` | none | Fail-closed input validation |
| Service | `app/Services/<Name>Service.php` | `<Name>Service.php` | models | Business logic (the only layer that thinks) |
| Model | `app/Models/<Name>.php` | `<Name>.php` | none | Eloquent model; `$fillable`/`$guarded` set |
| Route | `routes/api.php` | `api.php` | controllers | One route group per resource |
| Error shaper | `app/Exceptions/Handler.php` | `Handler.php` | none | The ONLY error-response shaper |
| Test | `tests/Feature/<Name>Test.php` | `<Name>Test.php` | source under test | PHPUnit / Pest |

## 3. Entity recipes

### Add a new endpoint
- **Trigger:** "add `POST /<resource>`".
- **Files emitted:**
  1. `app/Http/Controllers/<Name>Controller.php`
  2. `app/Http/Requests/<Name>Request.php`
  3. `app/Services/<Name>Service.php`
- **Steps:**
  1. Controller type-hints the Form Request (validation runs first) + the service.
  2. Service does the work, returns a model/DTO; never `$request->all()` into a service.
  3. Register the route in `routes/api.php`.

### Add a new model
- **Trigger:** "persist `<Entity>`".
- **Files emitted:** `app/Models/<Name>.php` + `database/migrations/<ts>_create_<table>.php`.
- **Steps:**
  1. Set `$fillable`; eager-load relations with `with()` (no N+1).

### Add a new test
- **Trigger:** any new endpoint / service.
- **Files emitted:** `tests/Feature/<Name>Test.php` / `tests/Unit/<Name>Test.php`.
- **Steps:**
  1. Feature test hits the route (happy + error); unit-test the service per method.

## 4. Conventions

#### Naming
- Classes / files: `PascalCase` (`OrderService.php`). Methods: `camelCase`.

#### Test colocation
- Mirrored: `tests/Feature/<Name>Test.php` mirrors the controller/service.

#### Dependency rules
- ✓ controller → service → model.
- ✗ no business logic in routes; no `env()` outside `config/`.
- ✗ `src/backend/` never imports from `src/frontend/` / `src/mobile/` — share via `src/shared/`.
