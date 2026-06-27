---
globs: ["src/frontend/**/*.{ts,tsx,astro}"]
alwaysApply: false
---

# Astro Frontend Rules (auto-loaded on src/frontend/**/*.{ts,tsx,astro})

When editing any Astro, TypeScript, or TSX file under `src/frontend/` in an Astro project, follow these standards:

- **Static-first rendering** — `output: "static"` is the default; a page ships zero JS unless an island opts in.
- **Minimal hydration** — an island uses the narrowest `client:*` directive that works (`client:visible` over `client:load`); never hydrate what static HTML can render.
- **Islands are leaves** — interactive framework components are extracted leaf islands, not wrappers around `.astro` content.
- **Content collections are the SSOT** — every content type has a Zod schema in `src/content/config.ts`; querying frontmatter ad-hoc is a review finding.
- **One error shaper** — only `src/lib/problem.ts` writes API error bodies; endpoints return typed errors, not hand-built JSON.
- **Strict TypeScript** — `astro check` is the lint gate; `any` requires a written justification.
- **Build-time data** — `.astro` frontmatter runs at build (SSG); never assume a request context unless the route is explicitly server-rendered.

Canonical policy: `docs/engineering/astro-rules.md`
Playbook: `docs/playbooks/astro-app.md`
Primary skill: `astro`
