<!-- domain:FRONTEND | layer:rules | ssot:true | updated:2026-01-01 -->
# Nuxt Engineering Rules

Purpose: Non-negotiable conventions for the cos-golden-fixture Nuxt frontend.
Read when: Editing anything under `src/frontend/`.
Skip when: Backend/mobile work.
Read next: [Nuxt App Playbook](../playbooks/nuxt-app.md)

> Nav: [Master Index](../00-index.md)

## Hard rules

1. **SSR-safe fetching** — `useFetch`/`useAsyncData` in setup; bare `$fetch`
   only in event handlers and server routes (hydration double-fetch is a
   review-blocking finding).
2. **Auto-import discipline** — no manual imports for Vue/Nuxt APIs,
   `components/`, or `composables/`; composables are `useThing()`, one per file.
3. **State hierarchy** — local `ref` → composable → Pinia store; no module-
   level mutable singletons.
4. **Client/server split** — secrets and privileged clients live under
   `server/`; a page import boundary is a publish boundary.
5. **Strict TypeScript** — `npm run lint` (vue-tsc) gates merges; `any` needs
   a written justification.
6. **A11y is not optional** — interactive elements keyboard-reachable with
   visible focus; checked per [accessibility-web](./accessibility-web.md).

## Testing bar

Composables unit-tested; components behavior-tested (no snapshot-only
suites); server routes invoked directly with mocked events.
