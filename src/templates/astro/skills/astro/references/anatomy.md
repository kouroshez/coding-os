<!-- domain:ASTRO | layer:reference | ssot:true | updated:2026-06-27 -->
# Astro Anatomy

> P: Canonical file map + entity recipes for the Astro (islands, content-collections) stack.
> R: Adding any `.astro`/`.ts`/`.mjs` under `src/frontend/`, or routing a frontend / content task.
> S: Reading backend / mobile code — wrong stack.
> N: [SKILL.md](../SKILL.md), [scaffold-boundary.yaml](../../../scaffold-boundary.yaml)

> Nav: [Skill](../SKILL.md)

---

## 1. Boundary

SSOT: `src/templates/astro/scaffold-boundary.yaml`.

## 2. Layout map

| Pattern | Location | Naming | Imports from | Description |
|---|---|---|---|---|
| Page / route | `src/pages/<route>.astro` | `<route>.astro` | components, content | File-based route; SSG, zero client JS by default |
| API endpoint | `src/pages/api/<name>.ts` | `<name>.ts` | `lib/problem.ts` | Returns problem-shaped JSON |
| Component | `src/components/<Name>.astro` | `<Name>.astro` | — | `.astro` markup; islands opt into `client:*` |
| Content collection | `src/content/<type>/` + `config.ts` | `config.ts` | `zod` | Typed content SSOT (schema-validated) |
| Error shaper | `src/lib/problem.ts` | `problem.ts` | none | The ONLY error-response writer (RFC 9457) |
| Test | `<file>.test.ts` | `<file>.test.ts` | source under test | Vitest |

## 3. Entity recipes

### Add a new component
- **Trigger:** "add a `<Name>` UI block".
- **Files emitted:** `src/components/<Name>.astro` (+ a leaf island only if interactive).
- **Steps:**
  1. Render static `.astro` markup; pass data via `Astro.props`.
  2. Hydrate only an extracted leaf island with the narrowest `client:*`.

### Add a new endpoint
- **Trigger:** "add `GET /api/<name>`".
- **Files emitted:** `src/pages/api/<name>.ts`.
- **Steps:**
  1. Export `GET`/`POST`; validate input; return `lib/problem.ts` shape on error.

### Add a new model
- **Trigger:** "add a `<type>` content collection".
- **Files emitted:** `src/content/config.ts` (schema) + `src/content/<type>/`.
- **Steps:**
  1. Define a `zod` schema in `config.ts`; query via `getCollection`.

### Add a new test
- **Trigger:** any new endpoint / island.
- **Files emitted:** `<file>.test.ts` next to source.
- **Steps:**
  1. Vitest unit for logic; `astro check` for types.

## 4. Conventions

#### Naming
- Components: `PascalCase.astro`. Routes / endpoints: `kebab-case`.

#### Test colocation
- Colocated: `<file>.test.ts` next to source.

#### Dependency rules
- ✓ page → component → content/lib.
- ✗ a page never writes an error body inline — use `lib/problem.ts`.
- ✗ `src/frontend/` never imports from `src/backend/` / `src/mobile/` — share via `src/shared/`.
