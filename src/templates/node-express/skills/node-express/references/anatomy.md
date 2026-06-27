<!-- domain:NODEEXPRESS | layer:reference | ssot:true | updated:2026-06-27 -->
# Express Anatomy

> P: Canonical file map + entity recipes for the Node + Express (layered, TypeScript) stack.
> R: Adding any `.ts` under `src/backend/`, or routing a backend task.
> S: Reading frontend / mobile code — wrong stack.
> N: [SKILL.md](../SKILL.md), [scaffold-boundary.yaml](../../../scaffold-boundary.yaml)

> Nav: [Skill](../SKILL.md)

---

## 1. Boundary

SSOT: `src/templates/node-express/scaffold-boundary.yaml`.

## 2. Layout map

| Pattern | Location | Naming | Imports from | Description |
|---|---|---|---|---|
| Router | `src/routes/<resource>.ts` | `<resource>.ts` | its service | One router per resource; thin handlers |
| Service | `src/services/<name>.ts` | `<name>.ts` | repository | Business logic (the only layer that thinks) |
| Repository | `src/repositories/<name>.ts` | `<name>.ts` | db client | Data access, one per aggregate |
| Middleware | `src/middleware/<name>.ts` | `<name>.ts` | none | Auth, validation, central error handler |
| Bootstrap | `src/index.ts` | `index.ts` | routes, middleware | App wiring — no logic |
| Test | `<file>.test.ts` | `<file>.test.ts` | source under test | Vitest / Jest + supertest |

## 3. Entity recipes

### Add a new endpoint
- **Trigger:** "add `POST /<resource>`".
- **Files emitted:**
  1. `src/routes/<resource>.ts`
  2. `src/services/<resource>.ts`
- **Steps:**
  1. Validate the body in middleware; the handler delegates to the service.
  2. Throw typed errors; the central error handler (last middleware) shapes them.
  3. Mount the router in `src/index.ts`.

### Add a new model
- **Trigger:** "persist `<Entity>`".
- **Files emitted:** `src/repositories/<name>.ts`.
- **Steps:**
  1. Repository owns the query; never a query in a service or handler.

### Add a new test
- **Trigger:** any new endpoint / service.
- **Files emitted:** `<file>.test.ts` next to source.
- **Steps:**
  1. `supertest` for routes (happy + error); mock the repo for service tests.

## 4. Conventions

#### Naming
- Files: `kebab-case.ts`. Functions: `camelCase`; types: `PascalCase`.

#### Test colocation
- Colocated: `<file>.test.ts` next to source.

#### Dependency rules
- ✓ router → service → repository.
- ✗ no business logic in middleware; error responses only from the central handler.
- ✗ `src/backend/` never imports from `src/frontend/` / `src/mobile/` — share via `src/shared/`.
