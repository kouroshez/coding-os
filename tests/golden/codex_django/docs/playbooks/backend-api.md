<!-- domain:ALL | layer:playbook | ssot:true | updated:2026-03-17 -->
# Backend API Playbook

Purpose: Execute Django/DRF work using architecture, schema, and service-layer SSOT without scanning unrelated docs.
Read when: The task touches backend apps, models, services, serializers, auth, payments, downloads, or admin APIs.
Skip when: The task is frontend-only, docs-only, or pure content work.
Read next: `docs/architecture/00-index.md`, then the relevant domain architecture doc.

> Nav: [Docs Index](../00-index.md) | [Architecture Index](../architecture/00-index.md)

## Task-to-File Mapping

Use this to select the exact architecture doc(s). If a task spans multiple domains, read the architecture doc for **each** domain — do not limit to one.

- Auth / login / registration / JWT → `architecture/04a-auth-security.md`
- Rate limiting / throttling / abuse protection → `architecture/04a-auth-security.md` + `architecture/04b-web-security.md`
- CSP / CORS / XSS / web security → `architecture/04b-web-security.md`
- File downloads / signed URLs → `architecture/04c-download-security.md`
- Payment / Stripe / checkout flow → `architecture/08-payment-architecture.md`
- Email / notifications / MJML → `architecture/07-email-notifications.md`
- Analytics / PostHog / events → `architecture/09-analytics-posthog.md`
- Blog / i18n / content backend → `architecture/10-blog-content-i18n.md`
- Testing / pytest / factories → `architecture/05-testing-strategy.md`
- Docker / infra / deployment → `architecture/06a-infrastructure.md` + `06b-docker-services.md`
- Identity / RBAC / roles / permissions → `PRD/12-schema-erd.md`
- New model / schema change → `architecture/03a-monorepo-layout.md` + `PRD/09-data-model-apis.md`
- Tech stack / dependency question → `architecture/02a-core-dependencies.md`

## Read Selection Guide

> Complete lookup: AGENTS.md § Dimension Type Registry (auto-loaded). This section adds domain-specific detail for Orient phase.

The Classify phase generates a Read List. Use this mapping to select files — do NOT read all entries. Read only what matches your task's dimensions and unknowns.

### By Dimension Type

| If task involves... | Read these files |
| --- | --- |
| Schema / model changes | `PRD/12-schema-erd.md` + `PRD/12c-indexing-strategy.md` |
| Business logic | `PRD/08-functional-requirements.md` |
| API contract shape | `api-contracts/{domain}.md` + `PRD/09-data-model-apis.md` |
| Auth / security | `architecture/04a-auth-security.md` + `security-review.md` |
| Payments | `architecture/08-payment-architecture.md` |
| Scheduled tasks / expiry | `architecture/06c-scheduled-tasks.md` |
| Frontend page context | `pages-content-spec/{page}.md` |
| Error handling patterns | `engineering/backend-rules.md` § Error Handling Policy |
| Testing patterns | `engineering/backend-rules.md` § Edge Case Testing |

### Always Read (for any backend task)

1. The exact architecture doc(s) from the Task-to-File Mapping above
2. `docs/engineering/backend-rules.md`

### Read Only If Relevant

- `docs/prd/12-schema-erd.md` — only if models/columns are touched
- `docs/prd/08-functional-requirements.md` — only if business logic involved
- `docs/playbooks/security-review.md` — only if the change is security-sensitive
- `docs/pages-content-spec/{page}.md` — only if the API serves a specific frontend page

## Execution Rules

- Business logic lives in `src/backend/apps/*/services/`.
- Schema names come from `PRD/12-schema-erd.md`; never invent model or field names.
- Monetary values stay in integer cents.
- Webhooks and payment truth come from provider webhooks, not client callbacks.
- Use `/api/v1/` routes and keep API changes version-safe.
- When existing code is found (Orient phase — repo search step), read existing serializers, tests, and factories in the same app to identify spec-vs-implementation gaps before writing new code.
- If task involves error handling or validation: also read `backend-rules.md` § Error Handling Policy
- If task involves testing: also read `backend-rules.md` § Edge Case Testing

## Verification

**Required** (enforced by `enforce-verify.sh` domain-aware hook):
1. `make lint-backend` — ruff + mypy
2. `make test-backend` — pytest (1178+ tests)
3. Both must show PASS in `.claude/.last-verify.json` within 30 min

**Additional**: if migrations created, agent prepares files but user runs `make migrate`. See AGENTS.md § Verification Matrix for full domain mapping.

## MVP Task Sequencing

Backend tasks are grouped by dependency order. Complete earlier groups before later ones:

1. **Foundation** (TASK-043, 044) → project structure, base models, settings
2. **Identity & Auth** (TASK-045–048) → user model, JWT, OAuth, email verification
3. **Catalog & Products** (TASK-049–051) → product model, categories, search
4. **Commerce & Cart** (TASK-052–054) → cart, checkout flow, order model
5. **Payments & Fulfillment** (TASK-055–057) → Stripe integration, webhooks, entitlements
6. **Downloads & Delivery** (TASK-058–059) → signed URLs, download tracking
7. **Content & Blog** (TASK-060–061) → blog backend, content API
8. **Notifications** (TASK-062–063) → email templates, notification service
9. **Reviews & Engagement** (TASK-064–065) → review system, favorites
10. **Analytics** (TASK-066–067) → PostHog events, tracking
11. **Admin Dashboard** (TASK-068–069) → admin APIs, dashboard data
12. **SEO & Technical** (TASK-070–071) → backend-owned sitemap, structured data
13. **Security & QA** (TASK-072–074) → security hardening, penetration testing
14. **Deployment** (TASK-075–077) → staging, production, monitoring

## Migration Workflow

Agent creates migration files; user runs `make migrate`. For safety rules, multi-step patterns, and rollback procedures, see `docs/engineering/backend-rules.md` § Migration Rules.

## SSOT Transition — Docs to Code

Design docs are read-once blueprints. After implementation, code is the living truth:

- Table schema → `models.py` (not `docs/prd/12a`, `12b`)
- Indexes → `models.py Meta.indexes` (not `docs/prd/12c`)
- API endpoints → `drf-spectacular` at `/api/v1/schema/` (not `docs/api-contracts/`)
- Business logic → `services.py` (not `docs/architecture/`)

Do NOT update design docs after implementation — code is SSOT. Live API docs: `/api/v1/docs/` (Swagger UI).

## Stop and Escalate If

- architecture docs conflict with schema docs
- the endpoint contract is missing from PRD/architecture — **do not infer endpoints from page specs alone; log a blocker via `cos task-move TASK-NNN --to blocked`**
- the change requires undocumented security behavior or provider semantics
