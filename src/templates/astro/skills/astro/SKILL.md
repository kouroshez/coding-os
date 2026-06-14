---
name: astro
tier: stack
domain: [frontend]
description: Use when creating or modifying files under src/frontend/ in an Astro app — .astro pages and components, islands (client:* directives), content collections (src/content/), API endpoints (pages/api/), and their config. Triggers on any .astro or .ts change under src/frontend/. Covers static-first SSG rendering, minimal island hydration, the typed content-collection SSOT, the single problem.ts error shaper, and build-time vs request-time boundaries. Generic UI patterns live in the core frontend-fundamentals skill.
globs: "src/frontend/**/*.{astro,ts}"
depends_on:
  - clean-code
  - frontend-fundamentals
  - a11y
last_reviewed: "2026-06-14"
---

REQUIRED BACKGROUND: You MUST also follow the core `frontend-fundamentals` skill (generic UI patterns) and `clean-code`. This skill adds Astro-specific patterns on top.

# astro

## Layer contract (matches `structure.tree`)

| Layer | May import | Never |
|---|---|---|
| `pages/*.astro` | layouts, components, `getCollection()` data | request-time globals (runs at build) |
| `components/*.astro` | child components, props | page-level data fetching for the whole page |
| islands (`client:*`) | the leaf framework component only | wrapping a whole page/layout |
| `pages/api/*.ts` | `lib/problem.ts`, domain logic | building an error body inline |
| `content/config.ts` | `astro:content`, Zod | runtime side effects |
| `lib/problem.ts` | nothing app-specific | leaking internals to the client |

Pages and `.astro` frontmatter run at **build time** (SSG) — no request
context there. Anything needing a request lives in an endpoint or an island,
so a page stays a static, zero-JS artifact.

## Rendering & islands

- `output: "static"` is the default; a page ships **zero client JS**. Switch a
  single route to `hybrid`/`server` only when it genuinely needs request-time
  rendering — never flip the whole app.
- Hydrate the **narrowest** island: `client:visible` / `client:idle` over
  `client:load`; `client:only` only when SSR truly cannot run.
- Islands are **leaf** components — extract the interactive part into a framework
  component (React/Svelte/Vue) and keep the page/layout shell static.

## Content collections

- Every content type has a Zod schema in `src/content/config.ts` — that schema
  is the content contract, validated at build time.
- Read via `getCollection()` / `getEntry()`; consume the typed `data`. Never read
  a frontmatter key the schema does not declare — extend the schema first.
- Collections are the content SSOT: content lives in `src/content/`, not inlined
  in pages.

## Endpoints

- A file under `pages/api/` exporting `GET`/`POST`/… is a server endpoint.
- Success returns a thin JSON `Response`; every error goes through the single
  `lib/problem.ts` shaper (RFC 9457, `docs/api-contracts/error-format.md`).
  Unknown errors → generic message to the client, full detail to the server log.

## SEO & metadata

- Per-page `<head>` (title/description/canonical/OpenGraph) is part of the page;
  the strategy + copy contract lives in `docs/playbooks/content-seo.md` — follow
  it rather than re-inventing metadata rules here.

## Testing

- Pages/components: `astro check` (strict TS) + `astro build` must be green — a
  build failure is the primary gate.
- Endpoints: cover happy + error path; assert the `problem()`-shaped body on
  failure.
- Content: at least one entry per collection so the Zod schema is exercised in CI.
