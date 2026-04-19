---
name: clean-code
description: Use when making any code change in the repository — frontend or backend. Enforces fail-closed error handling, self-documenting code, edge case awareness, and test coverage for error paths. Triggers on every commit that touches Python or TypeScript files.
globs: "**/*.{py,ts,tsx}"
context: fork
allowed-tools:
  - Read
  - Grep
  - Glob
---

This skill enforces universal coding principles on every code change in the NakoDigital monorepo. It applies to both frontend (TypeScript/Next.js) and backend (Python/Django) code equally.

## Pre-Code Checklist

Before writing any code, verify you have read the relevant context:

- [ ] Read the engineering doc for the domain being changed:
  - Frontend: `docs/engineering/frontend-rules.md`
  - Backend: `docs/engineering/backend-rules.md`
  - Naming: `docs/engineering/naming-conventions.md`
- [ ] If touching error handling or API responses: read `docs/api-contracts/` for the error format
- [ ] If touching auth, payments, or file uploads: read `docs/playbooks/security-review.md`
- [ ] Search the repo for existing patterns before introducing new ones

## 1. Error Handling: Fail-Closed Default

Every error handling decision defaults to **reject / deny / fail**. Never silently swallow errors.

### Principles

- If verification cannot complete: **reject** (not log-and-allow)
- If permission check fails: **deny access**
- If payment state is unclear: **do not fulfill**
- If external service is down: **fail the request** (not return stale/default data)

### Python — Correct

```python
# GOOD: fail-closed — unknown state rejects
def verify_purchase(user_id: str, product_id: str) -> Purchase:
    try:
        purchase = PurchaseService.get_verified(user_id, product_id)
    except PurchaseNotFoundError:
        raise PermissionDeniedError("Purchase not found")
    except VerificationError:
        logger.error("Purchase verification failed", extra={"user_id": user_id})
        raise ServiceUnavailableError("Unable to verify purchase")

    if purchase.status != PurchaseStatus.COMPLETED:
        raise PermissionDeniedError("Purchase not completed")

    return purchase
```

### Python — Wrong

```python
# BAD: fail-open — unknown state allows access
def verify_purchase(user_id, product_id):
    try:
        purchase = Purchase.objects.get(user_id=user_id, product_id=product_id)
        return purchase
    except Exception:
        # "Just log it" — user gets access anyway
        logger.warning("Could not verify purchase")
        return None  # caller treats None as "skip check"
```

### TypeScript — Correct

```typescript
// GOOD: fail-closed — catch re-throws, never swallows
async function fetchUserProfile(userId: string): Promise<UserProfile> {
  const response = await api.get(`/users/${userId}`);

  if (!response.ok) {
    throw new ApiError("Failed to fetch user profile", response.status);
  }

  return response.data;
}
```

### TypeScript — Wrong

```typescript
// BAD: fail-open — returns fallback on error, caller never knows
async function fetchUserProfile(userId: string) {
  try {
    const response = await api.get(`/users/${userId}`);
    return response.data;
  } catch {
    return { name: "Unknown", email: "" }; // silent fallback
  }
}
```

### Pattern Summary

| Situation | Correct (fail-closed) | Wrong (fail-open) |
|---|---|---|
| Unhandled exception | Re-raise or wrap in typed error | `except Exception: pass` |
| Permission check fails | Return 403 | Log and continue |
| Payment state unknown | Halt fulfillment | Fulfill and reconcile later |
| External service timeout | Return 503 | Return cached/default data |

## 1b. No PII in Logger Calls

Never pass PII (email, full name, IP address, phone) to any `logger.*` call. Use the user's UUID instead. If you need to log an email for debugging, use a masked form (`j***@example.com`). See `docs/engineering/logging-standards.md` for the full PII exclusion list.

```python
# GOOD
logger.error("Payment failed", extra={"user_id": user.id})

# BAD — leaks email
logger.error("Payment failed for %s", user.email)
```

## 1c. Never Manually Build Error Envelopes

Never construct error response dicts by hand (e.g., `return Response({"error_code": ...})`). Raise a typed exception and let the custom exception handler produce the envelope. See `docs/api-contracts/error-format.md`.

```python
# GOOD
raise ProductNotFoundError()

# BAD — bypasses exception handler, duplicates envelope logic
return Response({"error_code": "NOT_FOUND", "message": "Product not found"}, status=404)
```

## 2. No Internal Details in Responses

Never expose implementation details to API consumers.

### Forbidden in API responses

- `str(exc)` from any exception — may contain SQL, paths, or internal state
- Database column names, table names, or query fragments
- Stack traces or file paths
- Internal service names or infrastructure details

### Correct Pattern

```python
# GOOD: generic message to client, details in logs
except IntegrityError as exc:
    logger.error("Duplicate entry on user creation", extra={
        "email_hash": hash_email(data["email"]),
        "error": str(exc),
    })
    raise ConflictError("An account with this email already exists")
```

```typescript
// GOOD: generic error to UI, details in server logs
export async function createUser(data: UserInput) {
  const res = await api.post("/users/", data);

  if (res.status === 409) {
    throw new UserFacingError("An account with this email already exists");
  }

  if (!res.ok) {
    throw new UserFacingError("Something went wrong. Please try again.");
  }

  return res.data;
}
```

### Wrong Pattern

```python
# BAD: leaks DB details
except IntegrityError as exc:
    return Response(
        {"error": str(exc)},  # "duplicate key violates unique constraint users_email_key"
        status=409,
    )
```

## 3. Typed Exceptions

Use domain-specific exception classes. Never raise bare `ValueError` or `Exception`.

### Backend Convention

Each Django app defines exceptions in `apps/<domain>/exceptions.py`:

```python
# apps/products/exceptions.py
from apps.core.exceptions import AppError

class ProductNotFoundError(AppError):
    status_code = 404
    default_detail = "Product not found"

class ProductUnavailableError(AppError):
    status_code = 410
    default_detail = "Product is no longer available"
```

### Frontend Convention

Typed errors live in the relevant module or a shared errors file:

```typescript
// lib/errors.ts
export class ApiError extends Error {
  constructor(
    message: string,
    public statusCode: number,
    public code?: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export class UserFacingError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "UserFacingError";
  }
}
```

## 4. Self-Documenting Code

### Naming

Code reads like prose. Names reveal intent without needing comments.

```python
# GOOD
def calculate_discounted_price(base_price: Decimal, discount_pct: Decimal) -> Decimal:
    return base_price * (1 - discount_pct / 100)

# BAD
def calc(p, d):
    return p * (1 - d / 100)
```

```typescript
// GOOD
const isEligibleForRefund = order.status === "delivered" && daysSincePurchase <= 30;

// BAD
const flag = order.s === "d" && diff <= 30;
```

### Comments: Why, Not What

```python
# GOOD: explains business rule
# Stripe requires idempotency keys for all payment creation requests
# to prevent duplicate charges during network retries.
idempotency_key = f"order-{order.id}-{attempt}"

# BAD: restates the code
# Set the idempotency key to order id and attempt
idempotency_key = f"order-{order.id}-{attempt}"
```

### TODOs Must Reference Tasks

```python
# GOOD
# TODO: TASK-042 — add rate limiting to download endpoint

# BAD — bare TODOs are forbidden
# TODO: add rate limiting later
# TODO: fix this
# FIXME: hack
```

### Function Design

- **Single responsibility** — one function does one thing
- **~20 lines max** — if longer, extract a helper
- **3-4 parameters max** — use a config/options object beyond that
- **Guard clauses first** — handle invalid state at the top, keep the happy path unindented

```python
# GOOD: guard clauses, single responsibility, clear flow
def process_download(user: User, product_id: str) -> DownloadUrl:
    if not user.is_verified:
        raise PermissionDeniedError("Email verification required")

    product = get_product_or_raise(product_id)

    if not product.is_downloadable:
        raise ProductUnavailableError("Product has no downloadable files")

    purchase = get_verified_purchase_or_raise(user.id, product.id)

    return generate_signed_download_url(purchase)
```

## 5. Edge Case Awareness

Before writing any function, ask:

| Question | Example |
|---|---|
| What if the input is `None`/`undefined`? | User passes no product ID |
| What if the input is empty? | Empty string, empty list, `{}` |
| What if the input is at a boundary? | Price of 0, quantity of max int |
| What if the external service is down? | Stripe timeout, S3 unreachable |
| What if there is concurrent access? | Two users buy the last item simultaneously |
| What if the data is stale? | Cached price after a price change |

Address these explicitly — with guard clauses, validation, or documented assumptions.

```python
# GOOD: explicit None/empty handling
def get_product_display_name(product: Product | None) -> str:
    if product is None:
        raise ProductNotFoundError("Product reference is missing")

    if not product.name or not product.name.strip():
        logger.warning("Product has empty name", extra={"product_id": product.id})
        return f"Product #{product.id}"

    return product.name.strip()
```

## 6. Test Error Paths

### Rules

- Every `try/except` block needs a test that triggers the `except` branch
- Every validation rule needs a test with invalid input
- Never write `test_does_not_crash` — assert the correct behavior
- Test the error type, message, and status code

### Python Test Example

```python
class TestVerifyPurchase:
    def test_returns_purchase_when_verified(self, verified_purchase):
        result = verify_purchase(verified_purchase.user_id, verified_purchase.product_id)
        assert result.id == verified_purchase.id
        assert result.status == PurchaseStatus.COMPLETED

    def test_raises_permission_denied_when_not_found(self):
        with pytest.raises(PermissionDeniedError, match="Purchase not found"):
            verify_purchase("nonexistent-user", "nonexistent-product")

    def test_raises_service_unavailable_on_verification_failure(self, mocker):
        mocker.patch(
            "apps.purchases.services.PurchaseService.get_verified",
            side_effect=VerificationError("upstream timeout"),
        )
        with pytest.raises(ServiceUnavailableError, match="Unable to verify"):
            verify_purchase("user-1", "product-1")
```

### TypeScript Test Example

```typescript
describe("fetchUserProfile", () => {
  it("returns profile data on success", async () => {
    mockApi.get.mockResolvedValue({ ok: true, data: mockProfile });

    const result = await fetchUserProfile("user-1");

    expect(result).toEqual(mockProfile);
  });

  it("throws ApiError on non-OK response", async () => {
    mockApi.get.mockResolvedValue({ ok: false, status: 404 });

    await expect(fetchUserProfile("user-1")).rejects.toThrow(ApiError);
    await expect(fetchUserProfile("user-1")).rejects.toMatchObject({
      statusCode: 404,
    });
  });
});
```

## Post-Code Checklist

After writing code, verify all eight points before committing:

- [ ] **Fail-closed:** Every error path rejects/denies/fails — no silent swallowing
- [ ] **No leaks:** No `str(exc)`, DB names, or stack traces in API responses
- [ ] **Typed errors:** All raised exceptions use domain-specific classes
- [ ] **Self-documenting:** Names reveal intent; comments explain why, not what
- [ ] **No bare TODOs:** Every TODO references a TASK-### number
- [ ] **Function hygiene:** Functions are ~20 lines, 3-4 params, guard clauses first
- [ ] **Edge cases:** None, empty, boundary, service-down, and concurrency considered
- [ ] **Error path tests:** Every except/catch branch has a corresponding test case
