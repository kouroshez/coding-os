<!-- domain:FRONTEND | layer:playbook | ssot:true | updated:{{DATE}} -->
# Nuxt App Playbook

Purpose: The recipe for adding pages, components, composables and server routes to {{PROJECT_NAME}}.
Read when: Any frontend feature or fix in src/frontend/.
Skip when: Backend/mobile work.
Read next: [Nuxt Engineering Rules](../engineering/nuxt-rules.md)

> Nav: [Master Index](../00-index.md)

## Add a page

1. Create `src/frontend/pages/<route>.vue` (`[param].vue` for dynamic segments).
2. Fetch SSR data with `useFetch`/`useAsyncData` — never bare `$fetch` in setup.
3. Cross-page state goes to a Pinia store; page-local state stays `ref`/`computed`.
4. Accessibility pass per [accessibility-web](../engineering/accessibility-web.md).
5. Test: component behavior via @vue/test-utils; composables as units.
6. Verify: `cd src/frontend && npm run lint && npm test`.

## Add a server route

`server/api/<name>.<method>.ts` with `defineEventHandler`; validate input
fail-closed; errors via `createError` in the shared problem shape.

## Anti-patterns

- Manual vue-router wiring — file-based routing is the contract.
- Redundant `import { ref } from 'vue'` — auto-imports own that.
- Secrets in any file a page imports — server-only code lives in `server/`.
