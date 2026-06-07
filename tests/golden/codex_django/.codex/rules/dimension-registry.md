# Dimension Registry

Auto-generated from all installed stacks. Use during Classify
phase to build your Read List.

## django

- **Django model / schema** (M) → `docs/engineering/backend-rules.md`, `docs/playbooks/backend-api.md`
- **DRF endpoint** (M) → `docs/playbooks/backend-api.md`, `docs/api-contracts/error-format.md`
- **Auth / permissions** (M) → `docs/playbooks/security-review.md`

## fastapi

- **API endpoint** (M) → `docs/playbooks/fastapi-service.md`, `docs/engineering/fastapi-rules.md`
- **Pydantic model** (M) → `docs/engineering/fastapi-rules.md`

## go

- **HTTP handler** (M) → `docs/playbooks/go-service.md`
- **Concurrency** (M) → `docs/engineering/go-rules.md`

## go-fiber

- **Fiber handler** (M) → `docs/playbooks/fiber-service.md`, `docs/engineering/fiber-rules.md`
- **Middleware / auth** (M) → `docs/engineering/fiber-rules.md`
- **Request validation / DTO** (M) → `docs/engineering/fiber-rules.md`, `docs/api-contracts/error-format.md`

## meta

- **MCP tool authoring (cos_*)** (M) → `docs/playbooks/mcp-tool-authoring.md`, `docs/engineering/mcp-error-envelope.md`, `docs/governance/mcp-tool-inventory.md`
- **Graph extractor / backend** (M) → `docs/engineering/graph_os-queries.md`, `docs/engineering/graph-hallucination-cures.md`
- **Hook authoring (src/core/hooks/)** (M) → `docs/playbooks/hook-authoring.md`, `src/core/hooks/registry.yaml`, `docs/engineering/hooks-reference.md`
- **Adapter authoring (src/adapters/<id>/)** (M) → `docs/playbooks/adapter-authoring.md`, `docs/adapters/claude-sdk.md`, `docs/engineering/adapter-parity.md`
- **Template / stack authoring (src/templates/<id>/)** (M) → `docs/playbooks/template-authoring.md`, `docs/architecture/meta-project.md`, `src/core/schemas/stack.schema.json`
- **CLI command authoring (cli/)** (M) → `docs/architecture/meta-project.md`
- **Hub / web routes (src/core/web/)** (M) → `docs/engineering/hub-architecture.md`
- **Board / Scrumban (src/core/board_os/)** (M) → `docs/governance/task-lifecycle.md`
- **Cognition / formula composer** (M) → `docs/adapters/claude-sdk.md`, `docs/governance/critical-rules.md`
- **Rule SSOT regen** (M) → `docs/architecture/meta-project.md`
- **Security review (overlay)** (M) → `docs/playbooks/security-review.md`, `src/core/rules/api-contract-discipline.md`

## nextjs

- **React component** (M) → `docs/engineering/frontend-rules.md`, `docs/playbooks/frontend-ui.md`
- **Page / route** (M) → `docs/engineering/frontend-rendering-rules.md`, `docs/playbooks/frontend-ui.md`
- **Content / SEO** (M) → `docs/playbooks/content-seo.md`, `docs/engineering/copywriting-standard.md`
- **i18n** (M) → `docs/engineering/i18n-policy.md`
- **Accessibility** (M) → `docs/engineering/accessibility-web.md`

## react-native

- **RN screen** (M) → `docs/playbooks/mobile-app.md`, `docs/engineering/mobile-rules.md`
- **RN component** (M) → `docs/engineering/mobile-rules.md`
- **Offline / sync** (M) → `docs/engineering/offline-first.md`, `docs/playbooks/mobile-app.md`
- **Native bridge** (M) → `docs/playbooks/mobile-app.md`
- **Accessibility** (M) → `docs/engineering/accessibility-mobile.md`
