<!-- domain:SVELTESVELTEKIT | layer:reference | ssot:true | updated:2026-06-27 -->
# Svelte + SvelteKit Anatomy

> P: Canonical file map + entity recipes for the SvelteKit (file-routing, load functions) stack.
> R: Adding any `.svelte`/`.ts` under `src/frontend/`, or routing a frontend task.
> S: Reading backend / mobile code — wrong stack.
> N: [SKILL.md](../SKILL.md), [scaffold-boundary.yaml](../../../scaffold-boundary.yaml)

> Nav: [Skill](../SKILL.md)

---

## 1. Boundary

SSOT: `src/templates/svelte-sveltekit/scaffold-boundary.yaml`.

## 2. Layout map

| Pattern | Location | Naming | Imports from | Description |
|---|---|---|---|---|
| Page | `src/routes/<path>/+page.svelte` | `+page.svelte` | `$lib` | Presentational route component |
| Universal load | `src/routes/<path>/+page.ts` | `+page.ts` | `$lib` | Runs client + server; owns page data |
| Server load | `src/routes/<path>/+page.server.ts` | `+page.server.ts` | db, secrets | Server-only data (secrets live here) |
| Component | `src/lib/components/<Name>.svelte` | `<Name>.svelte` | — | Reusable presentational UI |
| Store | `src/lib/stores/<name>.ts` | `<name>.ts` | — | One writable/derived store per file |
| Error shaper | `src/hooks.server.ts` | `hooks.server.ts` | none | `handleError` — the ONLY error shaper |
| Test | `<file>.test.ts` | `<file>.test.ts` | source under test | Vitest / Playwright |

## 3. Entity recipes

### Add a new component
- **Trigger:** "add a `<Name>` UI block".
- **Files emitted:** `src/lib/components/<Name>.svelte` (+ test).
- **Steps:**
  1. Props in, events out; no data fetching in a component.

### Add a new route
- **Trigger:** "add a `/<path>` page".
- **Files emitted:**
  1. `src/routes/<path>/+page.svelte`
  2. `src/routes/<path>/+page.ts` (or `+page.server.ts` for secrets)
- **Steps:**
  1. `load` returns data; the page renders it. Secrets only in `+page.server.ts`.

### Add a new test
- **Trigger:** any new component / load.
- **Files emitted:** `<file>.test.ts` next to source.
- **Steps:**
  1. Vitest for units; Playwright for route flows.

## 4. Conventions

#### Naming
- Components: `PascalCase.svelte`. Routes: `kebab-case` dirs with `+page`/`+layout` files.

#### Test colocation
- Colocated: `<file>.test.ts` next to source.

#### Dependency rules
- ✓ page → load → `$lib` (stores/components).
- ✗ secrets never leave `+page.server.ts` / `+server.ts` / `hooks.server.ts`.
- ✗ `src/frontend/` never imports from `src/backend/` / `src/mobile/` — share via `src/shared/`.
