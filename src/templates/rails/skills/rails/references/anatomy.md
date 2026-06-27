<!-- domain:RAILS | layer:reference | ssot:true | updated:2026-06-27 -->
# Rails Anatomy

> P: Canonical file map + entity recipes for the Rails (thin-controller, fat-model) API stack.
> R: Adding any `.rb` under `src/backend/`, or routing a backend task.
> S: Reading frontend / mobile code — wrong stack.
> N: [SKILL.md](../SKILL.md), [scaffold-boundary.yaml](../../../scaffold-boundary.yaml)

> Nav: [Skill](../SKILL.md)

---

## 1. Boundary

SSOT: `src/templates/rails/scaffold-boundary.yaml`.

## 2. Layout map

| Pattern | Location | Naming | Imports from | Description |
|---|---|---|---|---|
| Controller | `app/controllers/<domain>_controller.rb` | `<domain>_controller.rb` | its model | Thin — parse params, call model, render |
| Model | `app/models/<domain>.rb` | `<domain>.rb` | none | ActiveRecord — logic + validations |
| Concern | `app/controllers/concerns/<name>.rb` | `<name>.rb` | none | Cross-cutting mixin (auth, pagination) |
| Routes | `config/routes.rb` | `routes.rb` | controllers | The one routing table |
| Error shaper | `app/controllers/application_controller.rb` | — | none | `rescue_from` chain — the ONLY error shaper |
| Migration | `db/migrate/<ts>_<slug>.rb` | `<ts>_<slug>.rb` | none | Schema change, append-only |
| Test | `test/<type>/<name>_test.rb` | `<name>_test.rb` | source under test | Minitest / RSpec |

## 3. Entity recipes

### Add a new endpoint
- **Trigger:** "add `POST /<resource>`".
- **Files emitted:**
  1. `app/controllers/<domain>_controller.rb`
  2. route entry in `config/routes.rb`
- **Steps:**
  1. Controller parses strong params, calls the model, renders JSON.
  2. Errors bubble to the `rescue_from` chain in `ApplicationController`.

### Add a new model
- **Trigger:** "persist `<Entity>`".
- **Files emitted:**
  1. `app/models/<domain>.rb`
  2. `db/migrate/<ts>_create_<table>.rb`
- **Steps:**
  1. Validations + business logic on the model; avoid N+1 with `includes`.

### Add a new migration
- **Trigger:** schema change.
- **Files emitted:** `db/migrate/<ts>_<slug>.rb`.
- **Steps:**
  1. Append-only; reversible `change` or `up`/`down`.

### Add a new test
- **Trigger:** any new controller / model.
- **Files emitted:** `test/<type>/<name>_test.rb`.
- **Steps:**
  1. Controller test hits the route (happy + error); model test per public method.

## 4. Conventions

#### Naming
- Files: `snake_case.rb`. Classes: `PascalCase`; methods: `snake_case`.

#### Test colocation
- Mirrored: `test/models/<name>_test.rb` mirrors `app/models/<name>.rb`.

#### Dependency rules
- ✓ controller → model; shared behavior via concerns.
- ✗ no business logic in controllers or routes.
- ✗ `src/backend/` never imports from `src/frontend/` / `src/mobile/` — share via `src/shared/`.
