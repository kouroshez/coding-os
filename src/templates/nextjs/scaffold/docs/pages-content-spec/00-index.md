<!-- domain:CONTENT | layer:index | ssot:true | updated:{{DATE}} -->
# Pages & Content Specs — Index

Purpose: Navigation hub for per-page content specifications (copy, layout, validation, error states).
Read when: Implementing or modifying a specific page in the Next.js app.
Skip when: The task is purely backend or doesn't touch a user-facing page.
Read next: The numbered page spec relevant to your task.

> Nav: [Docs Index](../00-index.md)

## Files

Page specs follow the convention `NN-page-name.md` and are numbered roughly by user journey:

<!-- Add as pages are documented. Example:
- [01-home.md](./01-home.md) — Marketing home page
- [02-products-catalog.md](./02-products-catalog.md) — Catalog browse
- [07-checkout.md](./07-checkout.md) — Checkout flow
-->

(empty — populate as pages are designed)

## Format

Each page spec follows this structure:

```markdown
<!-- domain:CONTENT | layer:spec | ssot:true | updated:YYYY-MM-DD -->
# NN. Page Name

> Nav: [Content Index](./00-index.md)

## Route

`/path/to/page`

## Purpose

(why this page exists, conversion goal)

## Layout

(component tree, key sections, responsive behavior)

## Copy

(headlines, body text, CTAs, error messages — localized keys)

## Data

(API endpoints called, query params, loading states)

## States

- Loading
- Empty
- Error (per error code from api-contracts/error-format.md)
- Success / populated

## Analytics

(events fired, properties tracked)

## SEO

(title, meta description, structured data)

## Acceptance

- Given/When/Then criteria
```

## Authoring Rules

- Page specs are SSOT for copy and layout. Components reference these — never the other way around.
- All copy uses i18n keys, never hardcoded strings (see `../engineering/i18n-policy.md`).
- Error states map to error codes from `../api-contracts/error-format.md`.
- When implementation diverges, update the spec in the same PR.
