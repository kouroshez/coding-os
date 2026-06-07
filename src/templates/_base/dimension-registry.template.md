---
description: Dimension Type Registry — maps task dimensions to doc files for Classify phase Read List
globs: "**/*"
alwaysApply: true
---

# Dimension Type Registry

Use during Classify phase to build your Read List. Each file must have a REASON from your Dimension Map. Fallback: if no row matches, search `docs/` with Grep/Glob.

**Backend** — always include `engineering/backend-rules.md`

- Schema/models → `PRD/12-schema-erd.md` + `PRD/12c-indexing-strategy.md`
- Business logic → `PRD/08-functional-requirements.md`
- API contract → `api-contracts/{domain}.md` + `PRD/09-data-model-apis.md`
- Auth/security → `architecture/04a-auth-security.md`
- Payments → `architecture/08-payment-architecture.md`
- Scheduled tasks → `architecture/06c-scheduled-tasks.md`
- Email/notifications → `architecture/07-email-notifications.md`
- Analytics → `architecture/09-analytics-posthog.md`
- Realtime/SSE → `architecture/11-realtime-sse.md`
- Blog/i18n → `architecture/10-blog-content-i18n.md`
- Performance → `engineering/backend-rules.md` § Performance
- Error handling → `engineering/backend-rules.md` § Error Handling Policy
- Testing → `engineering/backend-rules.md` § Edge Case Testing
- App structure → `architecture/03a-monorepo-layout.md`
- Dependencies → `architecture/02a-core-dependencies.md`

**Frontend** — always include `engineering/frontend-rules.md`

- Page layout → `pages-content-spec/{page}.md`
- API integration → `api-contracts/{domain}.md`
- Design/styling → `STYLE_GUIDE.md` + relevant `docs/design/` sub-file
- Business logic → `PRD/08-functional-requirements.md`
- Error states → `engineering/frontend-rules.md` § Error Handling
- Responsive → `engineering/frontend-rules.md`
- i18n → `engineering/i18n-policy.md`
- Accessibility → `engineering/accessibility-web.md`
- Rendering → `engineering/frontend-rendering-rules.md`
- Testing → `engineering/frontend-rules.md` § Edge Case Testing

**Content & SEO** — always include exact page spec

- Content/copy → `pages-content-spec/{page}.md`
- SEO metadata → `PRD/04-information-architecture.md`
- Blog/i18n → `architecture/10-blog-content-i18n.md` + `engineering/i18n-policy.md`
- Tone/voice → `engineering/copywriting-standard.md`

**Infrastructure**

- Docker → `architecture/06a-infrastructure.md` + `architecture/06b-docker-services.md`
- CI/CD → `architecture/06a-infrastructure.md`
- Deployment → `architecture/06-deployment-infra.md`
- Logging → `engineering/logging-standards.md`

**Docs & Governance** — always include `AGENTS.md` + `governance/docs-system.md`

- Task system → `governance/task-lifecycle.md`
- Doc structure → `governance/docs-system.md`
- Workflow → `workflow-docs/workflow-guide.md`
- Formatting → `engineering/formatting-rules.md`

**Security Overlay** (add to any domain)

- Auth/JWT → `architecture/04a-auth-security.md`
- CSRF/CORS → `architecture/04b-web-security.md`
- Downloads → `architecture/04c-download-security.md`
- Compliance → `architecture/04d-compliance.md`
