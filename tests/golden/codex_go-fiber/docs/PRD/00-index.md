<!-- domain:PRODUCT | layer:index | ssot:true | updated:2026-01-01 -->
# Product Requirements — Index

Purpose: Navigation hub for the Product Requirements Document (PRD).
Read when: Starting a feature task that needs product context, or onboarding to the project.
Skip when: The active task already references a specific PRD section.
Read next: The relevant numbered section below.

> Nav: [Docs Index](../00-index.md)

## Suggested Structure

The PRD is split into focused files. Each section is optional — populate as the project grows. Recommended order:

- `01-snapshot-vision.md` — One-paragraph elevator pitch + 3-year vision
- `02-goals-kpis.md` — Business goals and measurable KPIs
- `03-users-jobs.md` — Personas + jobs-to-be-done
- `04-information-architecture.md` — Page tree, navigation, content types
- `05-ux-conversion.md` — Conversion funnel, key flows, success metrics
- `06-product-pricing.md` — Pricing model, plans, packaging
- `07-policies-legal.md` — Terms, refund policy, content moderation
- `08-functional-requirements.md` — Feature list with priorities
- `09-data-model-apis.md` — High-level data model and API surface
- `10-nfr-implementation.md` — Non-functional requirements (perf, security, scale)
- `11-appendices.md` — Glossary, references, acknowledgements
- `12-schema-erd.md` — Database schema diagram + table reference

## Format

Each PRD section follows the standard doc header:

```html
<!-- domain:PRODUCT | layer:spec | ssot:true | updated:YYYY-MM-DD -->
```

Followed by H1, then the four-line opening block (Purpose / Read when / Skip when / Read next).

## Authoring Rules

- Each section is the SSOT for its topic. Other docs link here, not the other way around.
- When implementation deviates from PRD, update PRD first, then code.
- Open product questions go in `../_meta/questions.md`, not inline.
- Decisions with long-term impact go in `../architecture/adr/`, not in PRD.
