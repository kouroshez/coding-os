<!-- domain:NESTJS | layer:reference | ssot:true | updated:2026-06-27 -->
# NestJS Anatomy

> P: Canonical file map + entity recipes for the NestJS (module, DI, class-validator) stack.
> R: Adding any `.ts` under `src/backend/`, or routing a backend task.
> S: Reading frontend / mobile code — wrong stack.
> N: [SKILL.md](../SKILL.md), [scaffold-boundary.yaml](../../../scaffold-boundary.yaml)

> Nav: [Skill](../SKILL.md)

---

## 1. Boundary

SSOT: `src/templates/nestjs/scaffold-boundary.yaml`.

## 2. Layout map

| Pattern | Location | Naming | Imports from | Description |
|---|---|---|---|---|
| Controller | `src/<feature>/<feature>.controller.ts` | `<feature>.controller.ts` | its provider | Thin — maps routes, delegates to the provider |
| Provider | `src/<feature>/<feature>.service.ts` | `<feature>.service.ts` | repository | Business logic (the only layer that thinks) |
| DTO | `src/<feature>/dto/<name>.dto.ts` | `<name>.dto.ts` | none | class-validator decorated request shape |
| Module | `src/<feature>/<feature>.module.ts` | `<feature>.module.ts` | feature files | Wires controller + providers |
| Common | `src/common/` | `<name>.filter.ts` | none | Global exception filter (only error shaper) |
| Test | `<file>.spec.ts` | `<file>.spec.ts` | source under test | Jest |

## 3. Entity recipes

### Add a new endpoint
- **Trigger:** "add `POST /<feature>`".
- **Files emitted:**
  1. `src/<feature>/<feature>.controller.ts`
  2. `src/<feature>/<feature>.service.ts`
  3. `src/<feature>/dto/<name>.dto.ts`
  4. `src/<feature>/<feature>.module.ts`
- **Steps:**
  1. Controller injects the provider via constructor; binds the DTO.
  2. Global `ValidationPipe` validates the DTO before the provider runs.
  3. Register the module in `app.module.ts`.

### Add a new model
- **Trigger:** "persist `<Entity>`".
- **Files emitted:** `src/<feature>/entities/<name>.entity.ts`.
- **Steps:**
  1. ORM entity; the repository owns persistence, never the controller.

### Add a new test
- **Trigger:** any new controller / provider.
- **Files emitted:** `<file>.spec.ts` next to source.
- **Steps:**
  1. `Test.createTestingModule`; mock the provider for controller specs.

## 4. Conventions

#### Naming
- Files: `kebab-case.controller.ts`, `kebab-case.service.ts`. Classes: `PascalCase`.

#### Test colocation
- Colocated: `<file>.spec.ts` next to source.

#### Dependency rules
- ✓ controller → provider → repository; inject by constructor (`private readonly`).
- ✗ never `new` a provider; a provider never imports `@Req`/`@Res`.
- ✗ `src/backend/` never imports from `src/frontend/` / `src/mobile/` — share via `src/shared/`.
