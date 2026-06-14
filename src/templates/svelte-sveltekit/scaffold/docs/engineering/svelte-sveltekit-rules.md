<!-- domain:FRONTEND | layer:rules | ssot:true | updated:{{DATE}} -->
# SvelteKit Engineering Rules

Purpose: Non-negotiable conventions for the {{PROJECT_NAME}} SvelteKit frontend.
Read when: Editing anything under `src/frontend/`.
Skip when: Backend/mobile work.
Read next: [SvelteKit App Playbook](../playbooks/svelte-sveltekit-app.md)

> Nav: [Master Index](../00-index.md)

## Hard rules

1. **Load functions own data** — fetch in `+page.ts` / `+page.server.ts` / `+layout.ts`
   with the injected `fetch`; components stay presentational. Fetching in a
   component `<script>` body is a review-blocking finding.
2. **File-based routing only** — a route is a directory under `routes/` with a
   `+page.svelte`; never hand-wire a client router. Dynamic segments use
   `[param]/`.
3. **State hierarchy** — local component state (`$state` / `let`) → `$lib/stores`
   `writable`/`derived` for cross-component state; one store per file, no module-
   level mutable singletons. State-management skill is the hierarchy SSOT.
4. **Client/server split** — secrets and privileged clients live only in
   `+page.server.ts`, `+server.ts`, and `hooks.server.ts`; anything a
   `+page.svelte` imports ships to the client.
5. **One error shaper** — `hooks.server.ts::handleError` shapes every unexpected
   error response (shape: `docs/api-contracts/error-format.md`); endpoints throw
   or return typed errors, never build an ad-hoc error body.
6. **Strict TypeScript** — `npm run lint` (svelte-check) gates merges; `any`
   needs a written justification.
7. **A11y is not optional** — interactive elements keyboard-reachable with
   visible focus; the `a11y` core skill is the checklist SSOT.

## Testing bar

`load` functions unit-tested as pure functions; components behavior-tested with
@testing-library/svelte (no snapshot-only suites); server endpoints invoked
directly with a mocked request event.
