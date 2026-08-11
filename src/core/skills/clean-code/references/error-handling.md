# Error Handling — Worked Pairs

Depth behind [clean-code](../SKILL.md) §1, §1b, §1c, §2, §3, §5 and §6. The
normative rules are stated in the SKILL; this file carries the BAD/GOOD pairs
and the test shapes that show what each rule looks like in real code.

Read it when a rule's shape is unclear, when reviewing an error path, or when
writing the first error-handling code in a new service. The SKILL alone is
enough to comply — this is the *why it looks like that*.

## §1 — Fail-Closed Default

### Python

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

The `BAD` version is dangerous precisely because it looks defensive. A bare
`except Exception` that returns `None` converts every unknown failure into the
one value callers already treat as "nothing to check" — the outage becomes a
permission bypass, and no alarm fires.

### TypeScript

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

## §1b — No PII in Logger Calls

```python
# GOOD
logger.error("Payment failed", extra={"user_id": user.id})

# BAD — leaks email
logger.error("Payment failed for %s", user.email)
```

Logs are replicated, retained, and read by more people than the database is. A
UUID answers every debugging question an email answers, and none of the
compliance ones.

## §1c — Never Manually Build Error Envelopes

```python
# GOOD
raise ProductNotFoundError()

# BAD — bypasses exception handler, duplicates envelope logic
return Response({"error_code": "NOT_FOUND", "message": "Product not found"}, status=404)
```

The hand-built envelope drifts the moment the shared format changes: the
handler is updated once, every hand-built copy silently keeps the old shape.

## §2 — No Internal Details in Responses

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

```python
# BAD: leaks DB details
except IntegrityError as exc:
    return Response(
        {"error": str(exc)},  # "duplicate key violates unique constraint users_email_key"
        status=409,
    )
```

That leaked string names the table, the column and the constraint — a free
schema map for anyone probing the endpoint.

## §3 — Typed Exceptions

### Backend (Python)

Each bounded context defines exceptions in its own `exceptions.py`: for Django
apps `apps/<domain>/exceptions.py`, for FastAPI services
`domain/<name>/exceptions.py`, for the coding-os meta-repo
`src/core/<subsystem>/exceptions.py`. The shape is framework-independent:

```python
# domain-local exceptions.py
from core.exceptions import AppError  # project's base AppError lives in a single shared module

class ProductNotFoundError(AppError):
    status_code = 404
    default_detail = "Product not found"

class ProductUnavailableError(AppError):
    status_code = 410
    default_detail = "Product is no longer available"
```

### Frontend

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

A typed exception carries its own status code and default message, so the
handler maps it without a lookup table that some new error forgets to join.

## §5 — Edge Cases, Handled Explicitly

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

Each branch is a decision the reader can audit: a missing reference rejects, an
empty name degrades to a stable label and leaves a trace.

## §6 — Test the Error Paths

### Python

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

### TypeScript

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

Each error test names the exception type *and* the message or status. A test
that only asserts "it threw" still passes after a refactor turns a 403 into a
500.
