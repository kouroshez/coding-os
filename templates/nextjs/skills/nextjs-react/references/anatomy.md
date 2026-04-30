<!-- domain:NEXTJS | layer:reference | ssot:true | updated:2026-04-29 -->
# Next.js Anatomy

> P: Canonical file map and entity recipes for the Next.js stack — agents read this BEFORE writing any frontend file.
> R: Adding any `.ts` / `.tsx` file, or routing a frontend task.
> S: Working on backend / mobile / ai-service code.
> N: [SKILL.md](../SKILL.md), [scaffold-boundary.yaml](../../../scaffold-boundary.yaml)

> Nav: [Skill](../SKILL.md)

---

## 1. Boundary

SSOT: [`templates/nextjs/scaffold-boundary.yaml`](../../../scaffold-boundary.yaml).

## 2. Layout map

| Pattern | Location | Naming | Imports from | Description |
|---|---|---|---|---|
| Page route | `frontend/app/<segment>/page.tsx` | `page.tsx` (literal) | `@/components`, `@/lib` | Server Component default |
| Layout | `frontend/app/<segment>/layout.tsx` | `layout.tsx` (literal) | `@/components` | Wraps child route |
| Loading | `frontend/app/<segment>/loading.tsx` | `loading.tsx` (literal) | none | Streamed fallback |
| Error | `frontend/app/<segment>/error.tsx` | `error.tsx` (literal) | none | Client component |
| Not-found | `frontend/app/<segment>/not-found.tsx` | `not-found.tsx` | none | 404 surface |
| Component | `frontend/components/<area>/<name>.tsx` | `kebab-case.tsx` | `@/lib`, peers | Server-first |
| Client component | `frontend/components/<area>/<name>.client.tsx` | `<name>.client.tsx` | `@/lib` | `"use client"` |
| Hook | `frontend/lib/hooks/use<Name>.ts` | `useFooBar.ts` | none cross-area | Pure React hook |
| API helper | `frontend/lib/api/<resource>.ts` | `<resource>.ts` | `@/shared/types` | Server-only fetch |
| Utility | `frontend/lib/utils/<name>.ts` | `kebab-case.ts` | none cross-area | Stack-agnostic |
| Type module | `frontend/lib/types/<name>.ts` | `<name>.ts` | none | Frontend-shared types |
| Test | `frontend/<…>.test.{ts,tsx}` | `<file>.test.tsx` | source under test | Colocated |
| E2E | `frontend/e2e/<flow>.spec.ts` | `<flow>.spec.ts` | none | Playwright |
| Style module | `frontend/components/<area>/<name>.module.css` | `<name>.module.css` | none | CSS Modules |

## 3. Entity recipes

### Add a new component

- **Trigger:** "add a Foo component", "build a card / button / form".
- **Files:**
  1. `frontend/components/<area>/<name>.tsx`
  2. `frontend/components/<area>/<name>.test.tsx`
- **Steps:**
  1. Server Component default; client only if uses hooks / state / browser API.
  2. Author component with exported `interface <Name>Props`.
  3. Author colocated test (Given/When/Then).
  4. Re-export from `frontend/components/<area>/index.ts` only when cross-area imports needed.
- **Generator:** [`scripts/new_component.py`](../scripts/new_component.py).

### Add a new page / route

- **Trigger:** "add /pricing page", "new route".
- **Files:**
  1. `frontend/app/<segment>/page.tsx`
  2. `frontend/app/<segment>/loading.tsx` (recommended)
  3. `frontend/app/<segment>/error.tsx` (when route fetches data)
- **Steps:**
  1. Decide segment hierarchy — share layouts via parent `layout.tsx`.
  2. Server-fetch in `page.tsx`; never `useEffect` server-side.
  3. Add `export const metadata`.
  4. Wrap user-specific data in `<Suspense>` + `loading.tsx`.

### Add a new hook

- **Trigger:** "extract logic into a hook", "add useFoo".
- **Files:**
  1. `frontend/lib/hooks/use<Name>.ts`
  2. `frontend/lib/hooks/use<Name>.test.ts`
- **Steps:**
  1. Hook MUST start with `use`; client-only.
  2. Memoize stable values; expose typed return.
  3. Test renders consumer with mocked deps.

### Add a new API helper

- **Trigger:** "add wrapper for X endpoint", "fetch user profile".
- **Files:**
  1. `frontend/lib/api/<resource>.ts` (Server-Component only)
  2. `frontend/lib/api/<resource>.test.ts`
- **Steps:**
  1. `fetch` from a Server Component; auth via cookies.
  2. Return parsed types; never raw `Response`.
  3. Map errors to envelope from `shared/contracts/errors.ts`.
  4. NEVER import from `frontend/components/`.

### Add a new test

- **Trigger:** every component / hook / helper requires a colocated test.
- **Files:**
  1. `<source>.test.{ts,tsx}` — same dir as source.
- **Steps:**
  1. Vitest or Jest per project config.
  2. Author Given/When/Then; cover happy + ≥1 failure path.

## 4. Conventions

#### Naming

- Files: `kebab-case.{ts,tsx,css}` — exception: special Next.js names (`page.tsx`, `layout.tsx`, …).
- Components: `PascalCase` exported symbol.
- Hooks: `useCamelCase` symbol; file `useCamelCase.ts`.
- Constants: `SCREAMING_SNAKE_CASE`.
- CSS Modules: `<component>.module.css` next to source.

#### Test colocation

Colocated. `users/user-card.tsx` ⇄ `users/user-card.test.tsx`. E2E lives under `frontend/e2e/`. No `__tests__/` mirror dirs.

#### Dependency rules

- ✓ `frontend/` may import from `shared/`, `shared/types/`, `shared/contracts/`.
- ✗ `frontend/` may NOT import from `backend/`, `mobile/`, `ai-service/`.
- ✓ `frontend/components/` may import from `frontend/lib/`.
- ✗ `frontend/lib/` may NOT import from `frontend/components/` (one-way).
- ✗ Server Components may NOT import client-only hooks.
