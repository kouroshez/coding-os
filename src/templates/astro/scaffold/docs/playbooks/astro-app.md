<!-- domain:FRONTEND | layer:playbook | ssot:true | updated:{{DATE}} -->
# Astro App Playbook

Purpose: The end-to-end recipe for adding or changing a page, island, API endpoint, or content collection in the {{PROJECT_NAME}} Astro app.
Read when: Any task that adds a `.astro` page or component, a `pages/api/*` endpoint, or a content collection.
Skip when: SEO copy / metadata strategy — see the Content & SEO Playbook.
Read next: [Astro Engineering Rules](../engineering/astro-rules.md), [Content & SEO Playbook](./content-seo.md)

> Nav: [Master Index](../00-index.md)

## Add a page (the only sanctioned path)

1. **Pick the route** — a file under `src/frontend/src/pages/` IS the route
   (`pages/about.astro` → `/about`). Pages render at build time (SSG) and ship
   zero client JS by default.
2. **Static shell first** — write the page as a plain `.astro` file; pull data
   in the frontmatter fence (runs at build time only).
3. **Island only where needed** — extract any genuinely interactive UI into a
   framework component and hydrate it with the narrowest `client:*` directive
   (`client:idle`/`client:visible` over `client:load`). Everything else stays
   static HTML.
4. **Verify** — `cd src/frontend && npm run lint && npm run build`.

## Add an API endpoint

1. A file under `pages/api/` exporting `GET`/`POST`/… is a server endpoint.
2. Success returns a thin JSON `Response`; every error goes through the single
   `lib/problem.ts` shaper (RFC 9457, [error-format](../api-contracts/error-format.md)) —
   never build an error body inline.
3. An endpoint needs `output: "hybrid"` (or `"server"`) in `astro.config.mjs`;
   keep static pages static.

## Add a content collection

1. Define the collection schema (Zod) in `src/content/config.ts` — that schema
   is the content contract; frontmatter is validated at build time.
2. Add entries as `.md`/`.mdx` under `src/content/<collection>/`.
3. Read with `getCollection()`; the returned `data` is typed from the schema —
   never read a frontmatter key the schema does not declare.
4. SEO/metadata for those pages → [Content & SEO Playbook](./content-seo.md).

## Global wiring (set once)

`astro.config.mjs` owns `output` mode + integrations; `src/lib/problem.ts` owns
every error response. Both are configured once so all routes inherit them.

## Anti-patterns

- `client:load` on a component that does not need immediate interactivity —
  defaults to `client:idle`/`client:visible`.
- An error body built inside an endpoint — the `problem()` helper owns the shape.
- Reading a frontmatter key the collection schema does not declare — extend the
  schema in `config.ts` first.
- Server-rendering a page that could be static — keep `output: "static"`.
