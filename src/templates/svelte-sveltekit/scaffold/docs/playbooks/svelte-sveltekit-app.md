<!-- domain:FRONTEND | layer:playbook | ssot:true | updated:{{DATE}} -->
# SvelteKit App Playbook

Purpose: The recipe for adding routes, pages, components, stores and load functions to {{PROJECT_NAME}}.
Read when: Any frontend feature or fix in src/frontend/.
Skip when: Backend/mobile work.
Read next: [SvelteKit Engineering Rules](../engineering/svelte-sveltekit-rules.md)

> Nav: [Master Index](../00-index.md)

## Add a route

1. Create `src/frontend/src/routes/<path>/+page.svelte` (`[param]/` for dynamic segments).
2. Fetch data in `+page.ts` (universal) or `+page.server.ts` (server-only) `load` — use the injected `fetch`, never the bare global.
3. Keep the `.svelte` file presentational: props/`load` data in, markup out — no fetching in the component body.
4. Accessibility pass per the `a11y` core skill checklist (focus, landmarks, keyboard).
5. Test: component behavior via @testing-library/svelte; `load` functions as pure units.
6. Verify: `cd src/frontend && npm run lint && npm test`.

## Add a store

`src/frontend/src/lib/stores/<name>.ts` exporting a `writable`/`derived` — one
store per file. Subscribe in components with the `$store` auto-subscription;
never mutate a store from inside a `load` function.

## Add a server endpoint

`src/frontend/src/routes/<path>/+server.ts` exporting `GET`/`POST` handlers;
validate input fail-closed and return `json(...)`. Unexpected errors flow
through `hooks.server.ts::handleError` — never hand-shape an error response.

## Anti-patterns

- Manual route wiring or a client router — file-based routing is the contract.
- Fetching in a component's `<script>` body — data belongs in a `load` function.
- Secrets in any module a `+page.svelte` imports — server-only code lives in `+page.server.ts` / `+server.ts` / `hooks.server.ts`.
