<!-- domain:FRONTEND | layer:rules | ssot:true | updated:{{DATE}} -->
# Astro Engineering Rules

Purpose: Non-negotiable conventions for the {{PROJECT_NAME}} Astro frontend — islands, rendering mode, content collections, endpoints.
Read when: Editing anything under `src/frontend/`.
Skip when: Backend/mobile work.
Read next: [Astro App Playbook](../playbooks/astro-app.md)

> Nav: [Master Index](../00-index.md)

## Hard rules

1. **Static-first rendering** — `output: "static"` is the default; a page ships
   zero client JS unless it explicitly hydrates an island. Switching a route to
   `hybrid`/`server` is a deliberate, justified change, not a convenience.
2. **Minimal hydration** — an island uses the narrowest `client:*` directive
   that works: `client:visible`/`client:idle` over `client:load`; `client:only`
   only when SSR genuinely cannot run. Over-hydration is a review finding.
3. **Islands are leaves** — interactive framework components are extracted leaf
   components; the page/layout shell stays a static `.astro` file. Never wrap a
   whole page in a `client:*` island.
4. **Content collections are the content SSOT** — every content type has a Zod
   schema + a Content Layer `loader` in `src/content.config.ts`; entries are
   validated at build. Pages read
   via `getCollection()`/`getEntry()` and consume the typed `data` — reading an
   undeclared frontmatter key is a build-blocking finding.
5. **One error shaper** — only `src/lib/problem.ts` writes API error bodies
   (the canonical `{error:{code,message,request_id}}` envelope from
   `docs/api-contracts/error-format.md`); endpoints return its result and log
   full detail server-side, never leaking internals to the client.
6. **Strict TypeScript** — `astro check` is the lint gate (extends
   `astro/tsconfigs/strict`); `any` requires a written justification at the site.
7. **Build-time data** — `.astro` frontmatter runs at build (SSG); never assume
   request context there. Request-time logic lives in an endpoint or an island.

## Testing bar

Pages/components ≥ build green via `astro check` + `astro build`; endpoints ≥
happy + error path (the `problem()`-shaped response) covered; content schemas
exercised by at least one entry so the Zod contract is enforced in CI.
