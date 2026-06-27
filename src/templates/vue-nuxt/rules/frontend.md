---
globs: ["src/frontend/**/*.{vue,ts}"]
alwaysApply: false
---

# Nuxt Frontend Rules (auto-loaded on src/frontend/**/*.{vue,ts})

When editing any Vue or TypeScript file under `src/frontend/` in a Nuxt project, follow these standards:

- **SSR-safe fetching** — `useFetch`/`useAsyncData` in setup; a bare `$fetch` in setup double-fetches across server and client.
- **Auto-import discipline** — no manual imports for Vue/Nuxt APIs, composables, or components; rely on Nuxt auto-import so the bundle stays consistent.
- **State hierarchy** — local `ref` → composable → Pinia store; no module-level mutable singletons (they leak between requests under SSR).
- **Client/server split** — secrets and privileged clients live under `server/`; never ship them in a component or a public runtime config key.
- **Strict TypeScript** — `npm run lint` (vue-tsc) gates merges; `any` needs a written justification.
- **A11y is not optional** — interactive elements are keyboard-reachable with visible focus and a correct accessible name.

Canonical policy: `docs/engineering/nuxt-rules.md`
Playbook: `docs/playbooks/nuxt-app.md`
Primary skill: `vue-nuxt`
