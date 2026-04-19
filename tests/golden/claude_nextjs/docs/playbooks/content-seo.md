<!-- domain:CONTENT | layer:playbook | ssot:true | updated:2026-03-17 -->
# Content & SEO Playbook

Purpose: Execute copy, metadata, and AI/SEO tasks with canonical message contracts and route-aware constraints.
Read when: The task edits content specs, metadata, sitemap, robots, `llms.txt`, structured data, or AI-discovery files.
Skip when: The task is purely backend domain logic or infrastructure.
Read next: Exact content spec, `docs/PRD/04-information-architecture.md`, and `docs/architecture/10-blog-content-i18n.md`

> Nav: [Docs Index](../00-index.md) | [Content Specs Index](../pages-content-spec/00-index.md)

## Read Selection Guide

> Complete lookup: AGENTS.md § Dimension Type Registry (auto-loaded). This section adds domain-specific detail for Orient phase.

The Classify phase generates a Read List. Use this mapping to select files — do NOT read all entries. Read only what matches your task's dimensions and unknowns.

### By Dimension Type

| If task involves... | Read these files |
| --- | --- |
| Page content / copy | Exact page spec in `pages-content-spec/` |
| SEO metadata | `PRD/04-information-architecture.md` |
| Blog / i18n | `architecture/10-blog-content-i18n.md` + `engineering/i18n-policy.md` |
| Tone / voice | `engineering/copywriting-standard.md` |
| Structured data | `PRD/04-information-architecture.md` |
| Design constraints | `STYLE_GUIDE.md` |

### Always Read (for any content task)

1. The exact content spec being changed

### Read Only If Relevant

- `engineering/i18n-policy.md` — only if message keys involved
- `STYLE_GUIDE.md` — only if presentation constraints affect copy

## Execution Rules

- Content specs define meaning, constraints, and message namespaces.
- Locale message files define the rendered strings; do not hardcode UI copy in components.
- Use the exact route identity from the content spec and distinguish frontend `/admin/*` routes from Django `/nako-manage/`.
- For technical SEO in Next.js, align with `app/sitemap.ts` and `app/robots.ts`.
- For AI discovery, keep `llms.txt` concise and link out to canonical human-readable docs.

## Verification

- Confirm every edited spec includes `Namespace`, `Message Contract`, `Copy Constraints`, and `SEO Contract`
- If code changed, run the relevant lint/build command for the touched surface
- Check that metadata requirements remain semantically ordered and route-correct

## Stop and Escalate If

- product positioning conflicts with the PRD
- a message key contract is missing but the task requires non-hardcoded copy
- a legal/policy page needs factual or legal review beyond existing SSOT
