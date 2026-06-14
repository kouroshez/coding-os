---
name: svelte
tier: stack
domain: [frontend]
description: Use when creating or modifying Svelte/TypeScript files under src/frontend/ in a SvelteKit app — routes (+page/+layout), load functions, .svelte components, $lib stores, and server endpoints (+server.ts). Triggers on any .svelte or .ts change under src/frontend/. Covers file-based routing, universal vs server load, the $lib stores hierarchy, the single hooks.server.ts error shaper, and the client/server publish boundary. Generic frontend principles live in the core frontend-fundamentals skill.
globs: "src/frontend/**/*.{svelte,ts}"
depends_on:
  - clean-code
  - frontend-fundamentals
  - state-management
last_reviewed: "2026-06-14"
---

REQUIRED BACKGROUND: You MUST also follow the core `frontend-fundamentals` and `clean-code` skills. This skill adds SvelteKit-specific conventions on top.

# svelte

## Layer contract (matches `structure.tree`)

| Layer | May import | Never |
|---|---|---|
| `+page.svelte` / components | `$lib` components + stores, `load` data via props | `fetch` in setup, server-only modules, secrets |
| `+page.ts` / `+layout.ts` (universal) | the injected `fetch`, public env | `$env/static/private`, db clients, secrets |
| `+page.server.ts` / `+server.ts` (server) | db clients, private env, secrets | DOM, browser-only APIs |
| `$lib/stores/*.ts` | `svelte/store` primitives | route modules, `load` results |
| `hooks.server.ts` | private env, the logger | per-route business logic |

Components stay presentational — data arrives as props from a `load` function —
so a fetch swap is a `load`-layer-only change and the component is unit-testable
without a network.

## Routing & layout

- File-based routing only — a route is a directory under `routes/` with a
  `+page.svelte`; never hand-wire a client router. Dynamic segments: `routes/users/[id]/+page.svelte`.
- `+layout.svelte` owns shared shell (nav, error boundary) and renders the page
  via `{@render children()}`; keep it a shell, not a logic host.

## Load functions (data ownership)

- `+page.ts` / `+layout.ts` (universal) run on server then client — use the
  injected `fetch`, never the bare global (it double-fetches on hydration and
  skips SvelteKit's relative-URL + cookie handling).
- `+page.server.ts` / `+layout.server.ts` run server-only — the place for db
  clients, `$env/static/private`, and any secret. Their return value is
  serialized to the client, so never return a secret from a server `load`.
- A component never fetches in its `<script>` body; data flows in through the
  `load` result as `data` props.

## Stores & state

- Local component state first (`$state` / plain `let`); cross-component state in
  `$lib/stores` as `writable`/`derived`, one store per file, per the
  state-management skill hierarchy — no module-level mutable singletons.
- Subscribe with the `$store` auto-subscription in components; never manually
  `.subscribe()` without unsubscribing.
- Do not mutate a store from inside a `load` function — `load` returns data,
  stores hold client state.

## Client/server split (the publish boundary)

- Anything a `+page.svelte` imports ships to the browser. Secrets, privileged
  clients, and `$env/static/private` live only in `+page.server.ts`,
  `+server.ts`, and `hooks.server.ts`.
- A `+page.svelte` import of a server-only module is a publish-boundary leak and
  a review-blocking finding.

## Error handling

- ONE central shaper: `hooks.server.ts::handleError` shapes every unexpected
  server error (RFC-9457-style shape per `docs/api-contracts/error-format.md`).
  Log full detail server-side with a reference id; return only a safe message.
- Endpoints (`+server.ts`) and actions throw `error(status, ...)` /
  `fail(status, ...)`; never hand-build an error response body.

## Accessibility

- Interactive elements keyboard-reachable with a visible focus ring; use native
  elements (`<button>`, `<a>`) over `div` + handlers. Provide a skip link and a
  single `<main>` landmark in `+layout.svelte`. The `a11y` core skill is the
  checklist SSOT.

## Testing

- `load` functions: pure unit tests — call the exported `load` with a mocked
  event, assert the returned data; no network.
- Components: @testing-library/svelte, minimal mounting, assert behavior not
  markup; one happy + one error/empty state minimum.
- Server endpoints: invoke the `GET`/`POST` handler directly with a mocked
  request event; never bind a real port in tests.
