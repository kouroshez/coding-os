# Error Envelope — RFC 9457 Problem Details

The contract for every non-2xx response. Updated to RFC 9457 (March 2024, replaces RFC 7807). Used by the project's Go backend, FastAPI AI adapter, and surfaces straight into the React Native client's error handling.

## The Envelope

```http
HTTP/1.1 422 Unprocessable Entity
Content-Type: application/problem+json
Content-Language: en

{
  "type": "https://api.app.com/problems/validation-failed",
  "title": "Validation failed",
  "status": 422,
  "detail": "The 'email' field must be a valid email address.",
  "instance": "/users",
  "code": "validation_failed",
  "errors": [
    {
      "field": "email",
      "code": "invalid_email",
      "message": "must contain '@' and a domain"
    },
    {
      "field": "age",
      "code": "out_of_range",
      "message": "must be between 13 and 120"
    }
  ],
  "request_id": "req_8h2k4n9d3p7q",
  "documentation_url": "https://docs.app.com/errors/validation-failed"
}
```

## Field Definitions

| Field | Required | Stable across calls? | Description |
|---|---|---|---|
| `type` | yes | yes (per error class) | URI identifying the problem type. Treat as primary key. |
| `title` | yes | yes (per type) | Short human description. Frozen for a given `type`. |
| `status` | yes | yes (per type) | The HTTP status, repeated in body for client convenience. |
| `detail` | no | no (varies per occurrence) | Specific human explanation. Safe to render to users. |
| `instance` | no | no | URI of the specific occurrence (typically the request path). |
| `code` | yes (project convention) | yes (per type) | Short machine token. Snake_case. Stable across versions. |
| `errors[]` | conditional | structure stable | Field-level validation breakdown. Required for 422 validation failures. |
| `request_id` | yes (project convention) | no | Correlation id; matches `X-Request-Id` header. |
| `documentation_url` | no | yes | Optional link to docs page for this error class. |

### `type` URI Convention

```
https://api.app.com/problems/<problem-slug>
```

The URI does NOT need to dereference (RFC 9457 explicitly allows non-resolving URIs). But if you do publish docs there, use `documentation_url` to point to them so clients can deep-link without ambiguity.

### `code` vs `type` — Why Both?

- `type` is the wire format for machines that route on URLs / categorize problems.
- `code` is the project's snake_case shorthand. Easier to switch on in client code:

```typescript
switch (error.code) {
  case 'insufficient_funds': return showTopUpFlow();
  case 'rate_limited':       return scheduleRetry(error.retry_after);
  case 'validation_failed':  return highlightFields(error.errors);
}
```

Pick `code` first for client logic; `type` is the formal identifier.

## Error Catalogue

Maintain a **single source of truth** of error codes per service. New errors require a PR review like any other contract change.

```yaml
# docs/errors/catalogue.yaml — checked into the repo
errors:
  - code: validation_failed
    type: https://api.app.com/problems/validation-failed
    title: Validation failed
    status: 422
    notes: Use when request is well-formed but business rules reject it.

  - code: insufficient_funds
    type: https://api.app.com/problems/insufficient-funds
    title: Insufficient funds
    status: 402
    notes: Account balance below required amount.

  - code: rate_limited
    type: https://api.app.com/problems/rate-limited
    title: Too many requests
    status: 429
    extra_fields:
      - retry_after_seconds
    notes: Always include retry_after_seconds and Retry-After header.

  - code: unauthenticated
    type: https://api.app.com/problems/unauthenticated
    title: Authentication required
    status: 401

  - code: forbidden
    type: https://api.app.com/problems/forbidden
    title: Access denied
    status: 403

  - code: not_found
    type: https://api.app.com/problems/not-found
    title: Resource not found
    status: 404

  - code: conflict
    type: https://api.app.com/problems/conflict
    title: Conflict with current state
    status: 409
    notes: Lost updates, duplicate creates, state-machine violations.

  - code: idempotency_key_collision
    type: https://api.app.com/problems/idempotency-key-collision
    title: Idempotency key reused with different request
    status: 409
    notes: Same key, different body → reject not replay.

  - code: dependency_unavailable
    type: https://api.app.com/problems/dependency-unavailable
    title: Upstream service unavailable
    status: 503
    extra_fields:
      - retry_after_seconds
      - dependency_name

  - code: internal_error
    type: https://api.app.com/problems/internal-error
    title: Unexpected server error
    status: 500
    notes: Last-resort. detail must NOT leak stack/SQL/path info.
```

CI rule: any 4xx/5xx response in production logs whose `code` is not in the catalogue → fail the build / page on-call. Forces the catalogue to stay in sync with reality.

## Domain Error → HTTP Status Mapping

The hexagonal application layer raises domain errors; the inbound HTTP adapter maps them. Centralize the mapping in one helper.

```go
// pkg/apperr/from_domain.go
package apperr

import (
    "errors"

    "github.com/gofiber/fiber/v3"
    "myapp/internal/domain/order"
    "myapp/internal/domain/user"
)

func FromDomainError(c fiber.Ctx, err error) error {
    var (
        notFoundErr   *user.NotFoundError
        inactiveErr   *user.InactiveError
        invalidStateErr *order.InvalidStateError
        balanceErr    *order.InsufficientBalanceError
    )

    switch {
    case errors.As(err, &notFoundErr):
        return Problem(c, 404, "not_found", err.Error())
    case errors.As(err, &inactiveErr):
        return Problem(c, 403, "forbidden", "account is inactive")
    case errors.As(err, &invalidStateErr):
        return Problem(c, 409, "conflict", err.Error())
    case errors.As(err, &balanceErr):
        return Problem(c, 402, "insufficient_funds", err.Error())
    default:
        // Unknown domain error → log full, return generic to client.
        c.Locals("internal_error", err)
        return Problem(c, 500, "internal_error", "unexpected error")
    }
}
```

```python
# src/ai_adapter/delivery/http/error_handlers.py
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ai_adapter.application.usecase.send_message import (
    ConversationNotFound,
    MessageTooLong,
)


def install(app: FastAPI) -> None:
    @app.exception_handler(ConversationNotFound)
    async def conv_not_found(request: Request, exc: ConversationNotFound):
        return _problem(request, 404, "conversation_not_found", str(exc))

    @app.exception_handler(MessageTooLong)
    async def msg_too_long(request: Request, exc: MessageTooLong):
        return _problem(request, 422, "validation_failed", str(exc),
                        errors=[{"field": "user_text", "code": "too_long",
                                 "message": str(exc)}])


def _problem(request: Request, status: int, code: str, detail: str, **extra) -> JSONResponse:
    body = {
        "type": f"https://api.app.com/problems/{code.replace('_', '-')}",
        "title": _TITLE_BY_CODE[code],
        "status": status,
        "detail": detail,
        "instance": str(request.url.path),
        "code": code,
        "request_id": request.headers.get("X-Request-Id", ""),
        **extra,
    }
    return JSONResponse(
        body,
        status_code=status,
        headers={"Content-Type": "application/problem+json"},
    )
```

## Validation Errors — `errors[]` Shape

For 422 (and sometimes 400) where multiple field problems exist:

```json
{
  "type": "https://api.app.com/problems/validation-failed",
  "title": "Validation failed",
  "status": 422,
  "code": "validation_failed",
  "detail": "2 fields failed validation",
  "errors": [
    {
      "field": "items[0].quantity",
      "code": "min_value",
      "message": "must be at least 1",
      "constraint": { "min": 1 }
    },
    {
      "field": "promo_code",
      "code": "expired",
      "message": "promo code WELCOME10 expired on 2026-04-01"
    }
  ]
}
```

Per-error fields:

- `field` — JSON pointer or dotted path. Arrays use `[N]`.
- `code` — short token, e.g. `required`, `min_value`, `max_length`, `invalid_format`, `not_in_enum`.
- `message` — human-readable, safe to render.
- `constraint` (optional) — machine-readable bounds for client highlighting.

Always include the FULL list, not just the first failure. UX wants to highlight all bad fields at once.

## Status Code Decision Tree (for raisers)

```
Did the request fail before hitting business logic?
├─ Yes → 4xx
│   ├─ Auth missing → 401
│   ├─ Auth present but no permission → 403
│   ├─ Resource doesn't exist (or hide existence) → 404
│   ├─ HTTP method wrong for URL → 405
│   ├─ Body unparseable / type wrong → 400
│   └─ Body parsed but semantically invalid → 422
│
└─ No, it failed during business logic
    ├─ State conflict (lost update, duplicate) → 409
    ├─ Insufficient resource (balance, quota) → 402 (payment) | 403 (perm) | 422 (rule)
    ├─ Concurrent modification (ETag mismatch) → 412
    ├─ Rate limit hit → 429 (with Retry-After)
    ├─ Upstream service down → 502/503/504
    └─ Truly unexpected → 500
```

## What NEVER Goes in `detail`

- Stack traces.
- File paths (`/var/app/src/handlers/foo.py:142`).
- SQL fragments.
- Internal table or column names.
- Class names of internal exceptions.
- Information that would help an attacker (which user exists, which permission is missing).

The right way: log the full error server-side with `request_id` + payload, then return generic `detail` to the client. Support reads logs by `request_id`.

```python
# CORRECT
logger.error("DB integrity error on user create", extra={
    "request_id": req_id, "email_hash": h(email), "error": str(exc),
})
raise ConflictError("an account with this email already exists")

# WRONG
return JSONResponse({"detail": str(exc)}, status_code=409)
# detail = 'duplicate key value violates unique constraint "users_email_key"'
```

## RN Client Side — Consuming the Envelope

```typescript
// src/infrastructure/http/apiClient.ts
import axios, { AxiosError } from 'axios';

export interface ApiProblem {
  type: string;
  title: string;
  status: number;
  detail?: string;
  code: string;
  errors?: Array<{ field: string; code: string; message: string }>;
  request_id?: string;
  retry_after_seconds?: number;
}

export class ApiError extends Error {
  constructor(public problem: ApiProblem) {
    super(problem.title);
    this.name = 'ApiError';
  }
}

export const api = axios.create({ baseURL: 'https://api.app.com' });

api.interceptors.response.use(
  (res) => res,
  (err: AxiosError<ApiProblem>) => {
    if (err.response?.data?.code) {
      return Promise.reject(new ApiError(err.response.data));
    }
    // Network error, timeout, non-conforming server, etc.
    return Promise.reject(new ApiError({
      type: 'https://api.app.com/problems/network',
      title: 'Network error',
      status: 0,
      code: 'network_error',
      detail: err.message,
    }));
  },
);
```

Then in screens / use cases, switch on `error.problem.code`:

```typescript
try {
  await placeOrder.execute(input);
} catch (e) {
  if (e instanceof ApiError) {
    switch (e.problem.code) {
      case 'insufficient_funds': return navigation.navigate('TopUp');
      case 'rate_limited':       return showToast('Too fast, retrying…');
      case 'validation_failed':  return highlightFields(e.problem.errors);
      default:                   return showToast(e.problem.title);
    }
  }
  throw e;
}
```

## CI Enforcement

Three checks worth running:

1. **Catalogue completeness**: scan source for `code: "..."` literals; assert every one is in the YAML catalogue.
2. **Envelope shape**: every error response in integration tests is asserted against the JSON Schema for ProblemDetails.
3. **No leaked detail**: regex any error response body for SQL keywords (`SELECT`, `INSERT`, `constraint`), file paths (`/var/`, `/app/`), Python tracebacks (`Traceback`, `File "/`).

## References

- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457.html) (2024).
- [RFC 9745 — The Deprecation HTTP Header Field](https://www.rfc-editor.org/rfc/rfc9745.html) (2024).
- [JSON:API errors spec](https://jsonapi.org/format/#errors) — alternative envelope shape; useful comparison.
- Stripe Errors guide — <https://stripe.com/docs/api/errors>.
