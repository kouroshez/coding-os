<!-- domain:VUENUXT | layer:reference | ssot:true | updated:2026-06-27 -->
# Vue + Nuxt Anatomy

> P: Canonical file map + entity recipes for the Nuxt 3 (file-routing, composables, Pinia) stack.
> R: Adding any `.vue`/`.ts` under `src/frontend/`, or routing a frontend task.
> S: Reading backend / mobile code — wrong stack.
> N: [SKILL.md](../SKILL.md), [scaffold-boundary.yaml](../../../scaffold-boundary.yaml)

> Nav: [Skill](../SKILL.md)

---

## 1. Boundary

SSOT: `src/templates/vue-nuxt/scaffold-boundary.yaml`.

## 2. Layout map

| Pattern | Location | Naming | Imports from | Description |
|---|---|---|---|---|
| Page / route | `pages/<path>.vue` | `<path>.vue` | components, composables | File-based route; `useFetch` in setup |
| Component | `components/<Name>.vue` | `<Name>.vue` | — | Auto-imported, presentational |
| Composable | `composables/use<Name>.ts` | `use<Name>.ts` | stores | `useX()` state + data access logic |
| Store | `stores/<name>.ts` | `<name>.ts` | — | Pinia store, one per domain |
| Server route | `server/api/<name>.ts` | `<name>.ts` | — | Nitro endpoint (server-only) |
| Test | `<file>.test.ts` | `<file>.test.ts` | source under test | Vitest |

## 3. Entity recipes

### Add a new component
- **Trigger:** "add a `<Name>` UI block".
- **Files emitted:** `components/<Name>.vue` (+ test).
- **Steps:**
  1. `<script setup>`, props in / emits out; rely on auto-import.

### Add a new route
- **Trigger:** "add a `/<path>` page".
- **Files emitted:** `pages/<path>.vue` (+ `composables/use<Name>.ts` if it needs data).
- **Steps:**
  1. Fetch with `useFetch`/`useAsyncData` in setup — never a bare `$fetch`.
  2. Server-only logic and secrets go to `server/api/`.

### Add a new test
- **Trigger:** any new component / composable.
- **Files emitted:** `<file>.test.ts` next to source.
- **Steps:**
  1. Vitest + `@vue/test-utils`; `vue-tsc` for types.

## 4. Conventions

#### Naming
- Components: `PascalCase.vue`. Composables: `use<Name>.ts`; stores: `kebab-case.ts`.

#### Test colocation
- Colocated: `<file>.test.ts` next to source.

#### Dependency rules
- ✓ page → composable → Pinia store.
- ✗ no module-level mutable singletons (they leak across SSR requests).
- ✗ `src/frontend/` never imports from `src/backend/` / `src/mobile/` — share via `src/shared/`.
