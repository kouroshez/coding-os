<!-- domain:ALL | layer:policy | ssot:true | updated:2026-03-16 -->
# Backend Engineering Rules

Purpose: Canonical backend implementation policy for Django, DRF, Celery, PostgreSQL, and Redis work.
Read when: The task changes backend models, services, serializers, endpoints, auth, payments, downloads, or backend ops behavior.
Skip when: The task is frontend-only, docs-only, or pure content work.
Read next: `../architecture/00-index.md` and the matching domain architecture doc.

> Nav: [Docs Index](../00-index.md) | [CodeStyle](../../CodeStyle.md) | [Architecture](../architecture/00-index.md)

## Core Rules

- Schema changes happen through Django migrations only.
- Read operations use selectors in `apps/*/selectors/`. Never query ORM directly in views.
- Write operations use services in `apps/*/services/`. Views delegate, never mutate.
- Views are thin: parse request, call selector/service, return serialized response.
- Use integer cents for all monetary values.
- Payment and fulfillment flows must be idempotent.
- Long-running or retryable work goes through Celery tasks.

## Migration Rules

- Every migration must be reversible (`RunPython` requires `reverse_code`; `RunSQL` requires `reverse_sql`).
- Separate schema migrations from data migrations.
- Review generated SQL before production: `python manage.py sqlmigrate <app> <number>`.
- Test rollback locally: `migrate <app> <previous>` then re-apply.
- Migration-producing changes: agent creates files, **user runs `make migrate`**.
- **Add field with default:** `AddField(null=True)` → `RunPython(backfill)` → `AlterField(null=False)`.
- **Rename field:** `AddField(new_name)` → `RunPython(copy_data)` → `RemoveField(old_name)`.
- **Remove field:** stop reading/writing in code → deploy → `RemoveField` in next deploy.
- For large tables (>1M rows), test migration timing on staging before production.
- `django-pg-zero-downtime-migrations` prevents table locks; do not add manual `LOCK TABLE`.
- Never combine schema and data changes in the same migration file.

## Validation and Contracts

- Validate request payloads with DRF serializers.
- Validate cross-entity business rules in services.
- Use explicit error codes and the standard DRF exception wrapper from the common app.
- Keep API routes under `/api/v1/` unless versioning policy says otherwise.

## Security Baseline

- Use Django permissions and DRF permission classes; keep access-control language aligned with the current backend stack.
- Resolve client IPs through `django-ipware`, not `REMOTE_ADDR`.
- Keep JWT/session cookies `httpOnly`, `secure` in production, and `SameSite=Strict`.
- Validate uploaded files by content, not extension alone.
- Never expose internal stack traces or provider secrets in API responses.

## Error Handling Policy

- **Fail-closed default:** if verification/validation cannot complete, reject the operation. Never log-and-allow.
- Use typed exceptions from `apps/<domain>/exceptions.py`, inheriting `rest_framework.exceptions.APIException`.
- Never raise bare `ValueError` or `Exception` from service layer code.
- Never expose `str(exc)`, database column names, or third-party service details in API responses.
- Error responses must match the standard envelope in `docs/api-contracts/error-format.md`.
- The custom exception handler in `apps/common/exception_handler.py` formats all DRF exceptions automatically — use typed exceptions and it works.
- **Never manually build error envelopes** — do not write `return Response({"error_code": ..., "message": ...})`. Raise a typed exception instead; the handler produces the envelope.
- Every `except` block must either re-raise, raise a typed exception, or reject the operation. No silent `pass` or `return None`.
- Log internal error details at WARNING/ERROR level for debugging — generic message to client.

## Observability and Operations

- Log security-relevant events such as login failures, payment mutations, permission changes, and download denials.
- Capture 5xx failures through the analytics/error pipeline defined in architecture docs.
- Record architectural tradeoffs in the task file and `changes.log`, not in shadow logging files outside the task system.
- Use `.env` plus environment-specific Django settings modules for backend configuration.

## 8) System Health Diagnostics

The `systemhealth` Django management command validates the entire backend:

```bash
python manage.py systemhealth              # Full report (5 categories)
python manage.py systemhealth --json       # JSON output for CI
python manage.py systemhealth --category=security  # Single category
```

**Categories checked:**

- ENV VARIABLES: Stripe, Email, Turnstile, Storage, OAuth, PostHog
- CONNECTIONS: PostgreSQL (with latency), Redis (with latency)
- QUEUE & SCHEDULER: Celery broker, workers, beat, queue depth, failed tasks
- SECURITY: DEBUG, SECRET_KEY, HTTPS, CORS, CSRF, cookies
- MIGRATIONS: pending migration detection

**Makefile targets:**

- `make diagnose-backend` — run systemhealth in Docker
- `make diagnose-frontend` — validate frontend env vars + API reachability
- `make diagnose` — both combined
- `make ci-gate` — full pipeline including diagnostics

**When to run diagnostics:**

- After cloning the repo (verify env setup)
- During task verification (ensure services are healthy)
- Before deploy (part of `make ci-gate`)
- When debugging connection issues

## Required Security Review

Perform an explicit security review when the task touches: auth/sessions, payments/webhooks, file upload/download, HTML rendering/UGC, admin/privileged actions, redirects, CAPTCHA, rate limiting, or permission boundaries.

## Comments

- Comment **why**, not **what**. If the code is self-evident, no comment is needed.
- Use `Ref:` to trace decisions back to architecture docs (e.g. `# Ref: architecture/04a-auth-security.md`).
- Use `TODO: TASK-###` with a task number. Bare TODOs without a task reference are not allowed.
- Comment non-obvious ordering constraints, security rationale, and business rules.
- Do not add docstrings that restate the function name or arguments.

## Testing Standards

- **Infrastructure tests are mandatory**: `tests/test_infrastructure.py` must include `call_command("check", "--fail-level", "ERROR")` (catches admin field errors before they crash `runserver`) and `call_command("makemigrations", "--check", "--dry-run")` (catches missing migrations).
- For seeded data (permissions, feature flags, site settings): always use `get_or_create()` in tests, never `create()`, to avoid IntegrityError conflicts with data migrations.
- Every app must include: `tests/conftest.py` (shared fixtures), `tests/factories.py` (factory_boy factories), `tests/test_selectors.py`, `tests/test_api.py` (integration), `tests/test_contract.py` (schema assertions).
- Use `factory_boy` for test data. Avoid raw `Model.objects.create()` except in legacy fixtures.
- Factories live in `apps/<app>/tests/factories.py`; use `factory.Faker` for realistic values.
- Avoid hardcoded magic values — use factories with explicit overrides only for the fields under test.
- Verify N+1 prevention with `django_assert_num_queries` for selectors using `select_related`/`prefetch_related`; document expected query count in a comment.
- Define expected field sets as module-level constants; contract tests verify API response keys match exactly.
- Update contract field sets whenever a serializer changes.
- Target: 80%+ line coverage per app. Measure with `pytest --cov=apps/<app>`.

## Edge Case Testing

- Test null/None/empty inputs for every public service function and selector.
- Test boundary values (0, max allowed, max+1, negative for unsigned fields).
- Test error paths: what happens when the DB is down, Redis unavailable, Stripe returns 500?
- Test concurrent mutations for payment/order flows (idempotency verification).
- Never write a test that asserts "does not crash" — assert the correct behavior (correct error type, correct status code, correct state).
- Name edge-case tests descriptively: `test_create_order_when_cart_empty_returns_400`.
