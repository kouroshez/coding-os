---
globs: ["src/frontend/**/*.{svelte,ts}"]
alwaysApply: false
---

# SvelteKit Frontend Rules (auto-loaded on src/frontend/**/*.{svelte,ts})

When editing any Svelte or TypeScript file under `src/frontend/` in a SvelteKit project, follow these standards:

- **Load functions own data** — fetch in `+page.ts` / `+page.server.ts` / `+layout.ts` with the injected `fetch`; components stay presentational. Fetching in a component `<script>` body is a review-blocking finding.
- **File-based routing only** — a route is a directory under `routes/` with a `+page.svelte`; never hand-wire a client router. Dynamic segments use `[param]/`.
- **State hierarchy** — local component state (`$state` / `let`) → `$lib/stores` `writable`/`derived` for cross-component state; one store per file, no module-level mutable singletons.
- **Client/server split** — secrets and privileged clients live only in `+page.server.ts`, `+server.ts`, and `hooks.server.ts`; anything a `+page.svelte` imports ships to the client.
- **One error shaper** — `hooks.server.ts::handleError` shapes every unexpected error response; endpoints throw or return typed errors, never build an ad-hoc error body.
- **Strict TypeScript** — `npm run lint` (svelte-check) gates merges; `any` needs a written justification.
- **A11y is not optional** — interactive elements keyboard-reachable with visible focus; the `a11y` core skill is the checklist SSOT.

Canonical policy: `docs/engineering/svelte-sveltekit-rules.md`
Playbook: `docs/playbooks/svelte-sveltekit-app.md`
Primary skill: `svelte`
