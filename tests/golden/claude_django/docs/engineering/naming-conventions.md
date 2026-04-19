<!-- domain:ALL | layer:policy | ssot:true | updated:2026-03-13 -->
# Naming Conventions & Project Structure

Purpose: Canonical naming and placement policy for the actual NakoDigital monorepo.
Read when: Deciding where files belong, how they should be named, or how route/API names should look.
Skip when: The task already targets an existing file and no placement/naming decision is needed.
Read next: `../architecture/03-project-structure.md` or the relevant engineering rules file.

> Nav: [Docs Index](../00-index.md) | [CodeStyle](../../CodeStyle.md) | [Architecture](../architecture/00-index.md)

## Monorepo Anchors

- `frontend/` → Next.js application
- `backend/` → Django application
- `shared/` → shared contracts/constants
- `docs/` → SSOT docs
- `infrastructure/` → deploy, nginx, and operational scripts

## Frontend Placement

- Routes live in `frontend/app/`
- Shared UI primitives live in `frontend/components/ui/`
- Shared page sections live in `frontend/components/sections/`
- Feature-specific composite components live in domain folders such as `frontend/components/admin/`
- Message files live in `frontend/messages/`
- Route metadata and AI-discovery files follow Next.js conventions or `frontend/public/` where appropriate

## Backend Placement

- Django apps live in `backend/apps/`
- App-local business logic lives in `backend/apps/<domain>/services/`
- App-local tests live in `backend/apps/<domain>/tests/`
- Cross-app integration tests live in `backend/tests/`
- Settings live in `backend/config/settings/`

## Naming Rules

- Directories and non-class files → `kebab-case` for frontend, `snake_case` for backend Python modules
- React components, serializers, models, viewsets → `PascalCase`
- Functions and variables → `camelCase` in TypeScript, `snake_case` in Python
- Booleans → `is*`, `has*`, `can*`
- Django apps → `snake_case` singular names such as `accounts`, `catalog`, `admin_dashboard`
- URL paths → `kebab-case`
- API base path → `/api/v1/`
- Exception classes → `DomainActionError` pattern (e.g., `CartEmptyError`, `PaymentFailedError`, `EntitlementRevokedError`)
- Error codes → SCREAMING_SNAKE_CASE matching `docs/api-contracts/error-format.md` (e.g., `CART_EMPTY`, `PAYMENT_FAILED`)
- Validation functions → `validate_*` prefix (e.g., `validate_upload`, `validate_coupon_code`)
- Edge case tests → `test_<action>_when_<condition>_<expected>` (e.g., `test_create_order_when_cart_empty_returns_400`)

## Route Naming

- Frontend admin application routes use `/admin/*`
- Django admin stays at `/nako-manage/`
- Public product routes use slugs, not IDs, where the route contract already defines slugs

## Task and Doc Naming

- Task files → `TASK-###-slug.md`
- ADRs → `ADR-###-slug.md`
- Index files → `00-index.md`
- Historical governance docs → `YYYY-MM-topic.md`

## Import Order

1. React / Next.js
2. Third-party packages
3. Internal modules
4. Types
