<!-- domain:FRONTEND | layer:playbook | ssot:true | updated:{{DATE}} -->
# Content & SEO Playbook

Purpose: The recipe for content collections, metadata, structured data, and technical SEO in the {{PROJECT_NAME}} Astro app.
Read when: A task edits a content collection, page metadata, sitemap, robots, structured data, or AI-discovery files.
Skip when: The task is component/island UI behavior — see the Astro App Playbook.
Read next: [Astro App Playbook](./astro-app.md), [Astro Engineering Rules](../engineering/astro-rules.md)

> Nav: [Master Index](../00-index.md)

## Content collections (the sanctioned path)

- Define every collection with `defineCollection` + a Content Layer `loader` (`glob()`) + a zod schema in `src/content.config.ts`; frontmatter that fails the schema is a build error, not a silent default.
- Query with `getCollection` / `getEntry`; never glob-import markdown by hand.
- Keep rendered copy in the content entry — components receive typed props, they do not embed page prose.

## Metadata & technical SEO

- Centralize `<title>`, description, canonical, and Open Graph / Twitter tags in one layout or a `<SEO>` component; pages pass typed props, never hand-write `<meta>` ad hoc.
- Generate `sitemap.xml` via `@astrojs/sitemap` in `astro.config.mjs`; keep `robots.txt` in `public/` and aligned with the deployed canonical host.
- Emit structured data as JSON-LD in a `<script type="application/ld+json">` built from typed data, not string concatenation.

## AI discovery

- Keep `llms.txt` (in `public/`) concise and link out to canonical human-readable docs rather than duplicating them.

## Verification

- `npm run build` succeeds (schema-validates every content entry).
- Every indexable page resolves a canonical URL and a unique title + description.
- `sitemap.xml` and `robots.txt` reference the production host, not a preview URL.

## Stop and escalate if

- product positioning or page copy conflicts with the PRD.
- a content schema change would break already-published entries (plan a migration).
- a legal/policy page needs review beyond existing SSOT.
