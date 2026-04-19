---
name: python-django
description: Use when creating or modifying Python files in the backend/ directory — Django models, DRF views, serializers, services, selectors, Celery tasks, migrations, or tests. Triggers on any .py file change under backend/. Covers architecture patterns (services + selectors), exception hierarchy, error envelope, file upload validation, and testing standards specific to this Django/DRF codebase.
globs: "backend/**/*.py"
depends_on:
  - clean-code
  - backend-fundamentals
---

REQUIRED BACKGROUND: This skill `depends_on: [clean-code, backend-fundamentals]`. Both are loaded transitively — `clean-code` gives universal code quality (fail-closed errors, typed exceptions, self-documenting code, edge cases, error path tests) and `backend-fundamentals` gives stack-agnostic backend patterns (services/selectors, idempotency, envelopes, N+1, migrations, auth). This skill adds ONLY Django/DRF-specific layering on top.

## Pre-Code Checklist

Before writing any backend Python code, verify:

- [ ] Read `docs/engineering/backend-rules.md` — the canonical backend policy
- [ ] If touching models or schema: read `docs/PRD/12a-commerce-schema.md` and `docs/PRD/12b-content-and-system-schema.md`
- [ ] If touching API endpoints or error handling: read `docs/api-contracts/error-format.md`
- [ ] If touching auth, payments, file uploads, or permissions: read `docs/playbooks/security-review.md`
- [ ] If touching download infrastructure: read `docs/architecture/04c-download-security.md`
- [ ] Search the repo with Grep/Glob for existing code before creating any new file

## 1. Architecture: Services + Selectors

Views are thin dispatchers. All business logic lives in services (writes) and selectors (reads).

### Layer Responsibilities

| Layer | Location | Responsibility | Never Does |
|:------|:---------|:---------------|:-----------|
| View | `apps/*/views/` | Parse request, call service/selector, return response | ORM queries, business logic, mutations |
| Selector | `apps/*/selectors/` | Read-only ORM queries, filtering, aggregation | Write operations, side effects |
| Service | `apps/*/services/` | Business logic, validation, mutations, side effects | Direct HTTP response construction |
| Serializer | `apps/*/serializers/` | Request validation, response shaping | Business logic, ORM queries |

### Correct Pattern

```python
# apps/products/views/product_views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from apps.products.selectors import product_selectors
from apps.products.serializers import ProductDetailSerializer


class ProductDetailView(APIView):
    """Thin view — delegates to selector, serializes, returns."""

    def get(self, request, slug: str) -> Response:
        product = product_selectors.get_published_product(slug=slug)
        serializer = ProductDetailSerializer(product)
        return Response(serializer.data, status=status.HTTP_200_OK)
```

```python
# apps/products/selectors/product_selectors.py
from apps.products.models import Product
from apps.products.exceptions import ProductNotFoundError


def get_published_product(*, slug: str) -> Product:
    """Fetch a single published product by slug.

    Raises ProductNotFoundError if not found or not published.
    """
    try:
        return Product.objects.select_related("category", "creator").get(
            slug=slug, status="published"
        )
    except Product.DoesNotExist:
        raise ProductNotFoundError()
```

```python
# apps/products/services/product_service.py
from decimal import Decimal

from apps.products.models import Product
from apps.products.exceptions import ProductValidationError


def update_product_price(*, product: Product, new_price_cents: int) -> Product:
    """Update product price. Uses integer cents for all monetary values."""
    if new_price_cents < 0:
        raise ProductValidationError("Price cannot be negative")

    product.price_cents = new_price_cents
    product.save(update_fields=["price_cents", "updated_at"])
    return product
```

### Wrong Pattern

```python
# BAD: Fat view — queries ORM directly, contains business logic
class ProductDetailView(APIView):
    def get(self, request, slug):
        product = Product.objects.filter(slug=slug, status="published").first()
        if not product:
            return Response({"error": "not found"}, status=404)
        # Business logic in the view — violates architecture
        if product.price_cents == 0:
            product.is_featured = True
            product.save()
        return Response(ProductDetailSerializer(product).data)
```

## 2. Exception Hierarchy

Every Django app defines domain exceptions in `apps/<domain>/exceptions.py`. All inherit from `rest_framework.exceptions.APIException` (or a base class that does).

### Correct Pattern

```python
# apps/products/exceptions.py
from rest_framework.exceptions import APIException


class ProductNotFoundError(APIException):
    status_code = 404
    default_detail = "Product not found"
    default_code = "NOT_FOUND"


class ProductValidationError(APIException):
    status_code = 400
    default_detail = "Invalid product data"
    default_code = "VALIDATION_ERROR"


class ProductUnavailableError(APIException):
    status_code = 410
    default_detail = "Product is no longer available"
    default_code = "PRODUCT_UNAVAILABLE"
```

### Rules

- Every exception MUST define `status_code`, `default_detail`, and `default_code`
- `default_code` uses SCREAMING_SNAKE_CASE matching `docs/api-contracts/error-format.md`
- Never raise bare `ValueError`, `Exception`, or `RuntimeError` from services/selectors
- Never use `str(exc)` in responses — log it instead, return the typed error detail

### Wrong Pattern

```python
# BAD: bare exceptions leak internals and bypass the error envelope
def get_product(slug):
    product = Product.objects.filter(slug=slug).first()
    if not product:
        raise ValueError(f"No product with slug {slug}")  # WRONG
    return product
```

## 3. Error Response Envelope

All non-2xx responses MUST match the standard envelope from `docs/api-contracts/error-format.md`:

```json
{
  "error_code": "NOT_FOUND",
  "message": "Product not found",
  "details": {}
}
```

For validation errors (400):

```json
{
  "error_code": "VALIDATION_ERROR",
  "message": "One or more fields are invalid.",
  "errors": [
    { "field": "email", "error_code": "REQUIRED", "message": "This field is required." }
  ]
}
```

### How It Works

The custom exception handler in `apps/common/exception_handler.py` transforms DRF exceptions into this envelope automatically. As long as you raise typed exceptions (section 2), the envelope is handled for you.

```python
# apps/common/exception_handler.py (reference — do not recreate, already exists)
from rest_framework.views import exception_handler as drf_exception_handler


def custom_exception_handler(exc, context):
    response = drf_exception_handler(exc, context)
    if response is not None:
        response.data = {
            "error_code": getattr(exc, "default_code", "SERVER_ERROR"),
            "message": str(exc.detail) if hasattr(exc, "detail") else str(exc),
            "details": getattr(exc, "details", {}),
        }
    return response
```

Key points:

- Set `EXCEPTION_HANDLER` in DRF settings to point to this handler
- Typed exceptions auto-populate the envelope via `default_code` and `default_detail`
- Never construct error response dicts manually in views — raise the exception instead

## 4. File Upload Validation

All file uploads go through a validation pipeline. Ref: `docs/architecture/04c-download-security.md`.

### MIME Allowlists by Context

| Context | Allowed Types | Max Size |
|:--------|:-------------|:---------|
| `product_asset` | PDF, ZIP, DOCX, PPTX, XLSX, AI, PSD, FIGMA | 50 MB |
| `review_media` | JPG, PNG, WEBP | 5 MB |
| `avatar` | JPG, PNG, WEBP | 2 MB |
| `blog_image` | JPG, PNG, WEBP, GIF | 10 MB |

### Validation Rules

1. **Reject immediately** if: missing Content-Type, unknown/zero size, empty file body
2. **Magic byte verification** via `puremagic` — detected type must match the allowlist
3. **Fail-closed on detection errors** — if `puremagic` raises, reject the file
4. **Image validation** — for image contexts, open with Pillow and call `img.verify()`

### Correct Pattern

```python
# apps/common/services/file_validation_service.py
import puremagic
from PIL import Image
from django.core.exceptions import ValidationError


MIME_ALLOWLISTS = {
    "product_asset": {
        "application/pdf", "application/zip",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    },
    "review_media": {"image/jpeg", "image/png", "image/webp"},
    "avatar": {"image/jpeg", "image/png", "image/webp"},
    "blog_image": {"image/jpeg", "image/png", "image/webp", "image/gif"},
}

MAX_SIZES = {
    "product_asset": 50 * 1024 * 1024,
    "review_media": 5 * 1024 * 1024,
    "avatar": 2 * 1024 * 1024,
    "blog_image": 10 * 1024 * 1024,
}


def validate_upload(file, context: str) -> None:
    """Validate uploaded file against context-specific rules. Fail-closed."""
    if context not in MIME_ALLOWLISTS:
        raise ValidationError(f"Unknown upload context: {context}")

    if not file or file.size == 0:
        raise ValidationError("Empty file upload rejected")

    if file.size > MAX_SIZES[context]:
        raise ValidationError(
            f"File exceeds size limit of {MAX_SIZES[context] // (1024 * 1024)} MB"
        )

    # Magic byte verification — fail-closed on any error
    try:
        file.seek(0)
        detected = puremagic.from_stream(file)
        file.seek(0)
    except Exception:
        raise ValidationError("Unable to determine file type — upload rejected")

    if detected not in MIME_ALLOWLISTS[context]:
        raise ValidationError(
            f"File type '{detected}' not allowed for {context}"
        )

    # Additional image validation for image contexts
    if context in ("review_media", "avatar", "blog_image"):
        _validate_image(file)


def _validate_image(file) -> None:
    """Verify image integrity with Pillow."""
    try:
        img = Image.open(file)
        img.verify()
        file.seek(0)
    except Exception:
        raise ValidationError("Corrupted or invalid image file")
```

## 5. Testing Requirements

### Required Test Files Per App

Every Django app under `apps/` must have:

```
apps/<app>/tests/
    __init__.py
    conftest.py          # Shared fixtures (db access, authenticated client, etc.)
    factories.py         # factory_boy factories for all models in this app
    test_selectors.py    # Unit tests for selectors
    test_api.py          # Integration tests for API endpoints
    test_contract.py     # Schema/contract assertions (response shape)
```

### Factory Pattern

Use `factory_boy` for all test data. Never use raw `Model.objects.create()`.

```python
# apps/products/tests/factories.py
import factory
from apps.products.models import Product


class ProductFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Product

    name = factory.Faker("catch_phrase")
    slug = factory.LazyAttribute(lambda o: o.name.lower().replace(" ", "-"))
    price_cents = factory.Faker("random_int", min=100, max=50000)
    status = "published"
    creator = factory.SubFactory("apps.accounts.tests.factories.UserFactory")
```

### N+1 Prevention

Verify query counts with `django_assert_num_queries` for any selector using `select_related` or `prefetch_related`:

```python
# apps/products/tests/test_selectors.py
def test_get_published_products_avoids_n_plus_one(
    db, django_assert_num_queries, product_factory
):
    # Create 10 products with related category and creator
    product_factory.create_batch(10)

    # Expect exactly 1 query (with select_related joins)
    with django_assert_num_queries(1):
        list(product_selectors.get_published_products())
```

### Contract Tests

Verify API response shape matches the expected field set:

```python
# apps/products/tests/test_contract.py
PRODUCT_LIST_FIELDS = {
    "id", "name", "slug", "price_cents", "thumbnail_url",
    "category", "creator_name", "created_at",
}


def test_product_list_response_shape(auth_client, published_product):
    response = auth_client.get("/api/v1/products/")
    assert response.status_code == 200
    product_data = response.json()["results"][0]
    assert set(product_data.keys()) == PRODUCT_LIST_FIELDS
```

### Error Path Testing

Every service/selector that raises exceptions needs tests for each error path:

```python
# apps/products/tests/test_selectors.py
import pytest
from apps.products.exceptions import ProductNotFoundError
from apps.products.selectors import product_selectors


class TestGetPublishedProduct:
    def test_returns_product_when_found(self, db, published_product):
        result = product_selectors.get_published_product(slug=published_product.slug)
        assert result.id == published_product.id

    def test_raises_not_found_for_missing_slug(self, db):
        with pytest.raises(ProductNotFoundError):
            product_selectors.get_published_product(slug="nonexistent")

    def test_raises_not_found_for_draft_product(self, db, draft_product):
        with pytest.raises(ProductNotFoundError):
            product_selectors.get_published_product(slug=draft_product.slug)
```

### Coverage Target

- 80%+ line coverage per app: `pytest --cov=apps/<app>`
- Test error paths, not just happy paths
- Every `try/except` block needs a test that triggers the `except` branch

## 6. Migration Rules

Reference: `docs/engineering/backend-rules.md` § Migration Rules.

- Every migration must be reversible (`RunPython` needs `reverse_code`, `RunSQL` needs `reverse_sql`)
- Separate schema migrations from data migrations — never combine
- Add-field pattern: `AddField(null=True)` then `RunPython(backfill)` then `AlterField(null=False)`
- Agent creates migration files; **user runs `make migrate`**
- Review SQL before production: `python manage.py sqlmigrate <app> <number>`
- Use integer cents for all monetary values — never store prices as floats or decimals

## 7. Security Baseline

When the task touches any of these areas, ALSO read `docs/playbooks/security-review.md`:

- Auth / sessions / JWT
- Payments / webhooks
- File upload / download
- HTML rendering / UGC
- Admin / privileged actions
- Redirects / CAPTCHA / rate limiting
- Permission boundaries

Key rules:

- **No PII in logger calls** — never pass `user.email`, full name, or IP to `logger.*`. Use `user.id` (UUID) only. See `docs/engineering/logging-standards.md`.
- Use Django permissions + DRF permission classes
- Resolve client IPs through `django-ipware`, not `REMOTE_ADDR`
- JWT/session cookies: `httpOnly`, `secure`, `SameSite=Strict` in production
- Validate uploaded files by content (magic bytes), not extension alone
- Never expose stack traces or provider secrets in API responses
- Log security events: login failures, payment mutations, permission changes, download denials

## Post-Code Checklist

After writing backend Python code, verify all nine points before committing:

- [ ] **Architecture:** Views are thin — no ORM queries or business logic in views
- [ ] **Selectors/Services:** Read operations in selectors, write operations in services
- [ ] **Typed exceptions:** All exceptions inherit from `APIException` with `status_code`, `default_detail`, `default_code`
- [ ] **Error envelope:** Errors use the standard `{"error_code", "message", "details"}` shape via the custom handler
- [ ] **File uploads:** If applicable — magic byte verification, context-based allowlists, fail-closed
- [ ] **Migrations:** Reversible, schema/data separated, integer cents for money
- [ ] **Tests:** conftest.py, factories.py, test_selectors.py, test_api.py, test_contract.py all present
- [ ] **Coverage:** 80%+ line coverage, error paths tested, N+1 verified with `django_assert_num_queries`
- [ ] **Linting:** `ruff check` and `ruff format --check` pass; `pytest` passes
