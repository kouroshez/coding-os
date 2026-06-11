---
name: vue-nuxt
tier: stack
domain: [frontend]
description: Use when creating or modifying Vue/TypeScript files under src/frontend/ in a Nuxt 3 app — pages, components, composables, Pinia stores, and Nitro server routes. Triggers on any .vue or .ts change under src/frontend/. Covers file-based routing, auto-imports, SSR-safe data fetching, and composable conventions. Generic frontend principles live in the core frontend-fundamentals skill.
globs: "src/frontend/**/*.{vue,ts}"
depends_on:
  - clean-code
  - frontend-fundamentals
  - state-management
last_reviewed: "2026-06-11"
---

REQUIRED BACKGROUND: You MUST also follow the core `frontend-fundamentals` and `clean-code` skills. This skill adds Nuxt-3-specific conventions on top.

# vue-nuxt

## Routing & layout

- File-based routing only — a page is a file under `pages/`; never hand-wire
  vue-router. Dynamic segments: `pages/users/[id].vue`.
- `app.vue` stays a shell (`<NuxtLayout><NuxtPage/></NuxtLayout>`); layouts
  live in `layouts/`.

## Auto-imports (use them, don't fight them)

Components (`components/`), composables (`composables/`) and Vue/Nuxt APIs
auto-import. NO manual `import { ref } from 'vue'` — the linter treats a
redundant import as noise. Composables are named `useThing()` and live one
per file.

## Data fetching (SSR-safe)

- `useFetch`/`useAsyncData` in pages and components — never bare `$fetch` in
  setup (double-fetches on hydration).
- Bare `$fetch` is correct inside event handlers and server routes.
- Server-only secrets stay in `server/` — anything imported by a page ships
  to the client.

## State

Component-local `ref`/`computed` first; cross-page state in Pinia stores
(`stores/`, `useXStore` naming) per the state-management skill hierarchy —
no global reactive bags.

## Server routes

`server/api/<name>.<method>.ts` exporting `defineEventHandler`. Validate
input fail-closed; error responses use the shared problem shape
(`docs/api-contracts/error-format.md`) via `createError`.

## Testing

- Composables: unit tests, pure functions extracted where possible.
- Components: @vue/test-utils with minimal mounting; assert behavior, not
  markup details.
- Server routes: direct handler invocation with a mocked event.
