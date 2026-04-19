<!-- domain:ALL | layer:playbook | ssot:true | updated:2026-03-17 -->
# Frontend UI Playbook

Purpose: Execute frontend and UI tasks with the minimum required product, design, and engineering context.
Read when: The task changes routes, components, styling, layout, interactions, or frontend data boundaries.
Skip when: The task is backend-only, docs-only, or pure research.
Read next: Exact page spec, `STYLE_GUIDE.md`, and `docs/engineering/frontend-rules.md`

> Nav: [Docs Index](../00-index.md) | [Style Guide](../../STYLE_GUIDE.md)

## Read Selection Guide

> Complete lookup: AGENTS.md § Dimension Type Registry (auto-loaded). This section adds domain-specific detail for Orient phase.

The Classify phase generates a Read List. Use this mapping to select files — do NOT read all entries. Read only what matches your task's dimensions and unknowns.

### By Dimension Type

| If task involves... | Read these files |
| --- | --- |
| Page layout / content | `pages-content-spec/{page}.md` |
| API integration | `api-contracts/{domain}.md` |
| Design / styling | `STYLE_GUIDE.md` + relevant `docs/design/` sub-file |
| Business logic (user-facing) | `PRD/08-functional-requirements.md` |
| Error states / loading | `engineering/frontend-rules.md` § Error Handling |
| Responsive / mobile | `engineering/frontend-rules.md` § viewport rules |
| Testing | `engineering/frontend-rules.md` § Edge Case Testing |

### Always Read (for any frontend task)

1. The exact page/component being changed
2. `docs/engineering/frontend-rules.md`

### Read Only If Relevant

- Matching page spec in `docs/pages-content-spec/` — only if content/copy matters
- Matching API contract — only if data fetching involved
- `STYLE_GUIDE.md` — only if design/styling decisions needed

## Execution Rules

- Use exact copy from the content spec; do not improvise marketing copy.
- Prefer existing `components/ui`, `components/sections`, and shared patterns before creating new primitives.
- When existing components are found (Orient phase — repo search step), read existing tests, providers, and hooks in the same feature area to identify spec-vs-implementation gaps before writing new code.
- If task involves error states or API integration: also read `frontend-rules.md` § Error Handling
- If task involves testing: also read `frontend-rules.md` § Edge Case Testing
- Keep server/client boundaries explicit. Use client components only for real interaction.
- Treat `/admin/*` as frontend application routes and `/nako-manage/` as Django admin only.
- For SEO files, follow Next.js metadata conventions: `app/sitemap.ts`, `app/robots.ts`, and root AI-discovery files in `public/` or app metadata handlers as appropriate.

## Verification

**Required** (enforced by `enforce-verify.sh` domain-aware hook):

1. `cd frontend && npm run lint` — must show PASS in `.claude/.last-verify.json` within 30 min

**Additional**: visual smoke test at 375px, 768px, 1280px. If metadata or route generation changed, run `npm run build` when feasible. See AGENTS.md § Verification Matrix for full domain mapping.

## Stop and Escalate If

- the page copy conflicts with the content spec
- the route contract depends on an undefined API shape
- the task would introduce hardcoded copy where the spec expects message keys
