# REST Contract Patterns

The full pattern catalogue. Targets the project's stack (Go+Fiber, Python+FastAPI). Examples are minimal but production-shaped.

## URL Design

### Resources Are Plural Nouns

```
✓ GET    /orders           # collection
✓ POST   /orders           # create
✓ GET    /orders/{id}      # one
✓ PATCH  /orders/{id}      # partial update
✓ DELETE /orders/{id}      # delete

✗ GET    /order            # singular
✗ GET    /getOrder         # verb
✗ GET    /order/list       # verb
✗ POST   /order/create     # verb
```

### Hierarchy Reflects Ownership, Not Joins

```
✓ GET /orders/{id}/line-items                # line items belong to one order
✓ GET /users/{id}/orders                     # orders belong to one user

✗ GET /orders/{id}/customer/address/country  # too deep — flatten
✗ GET /tags/{id}/posts                       # M:N relationship — use ?tag=X instead
```

Cap nesting at **2 levels**. Beyond that, prefer flat URLs with query parameters or sub-resources mounted at the root.

### Filter / Sort / Project via Query Params

```
GET /orders?status=paid&user_id=usr_123&since=2026-01-01
GET /orders?sort=-created_at,amount        # `-` for descending
GET /orders?fields=id,total,status         # response shaping
```

Reserved meta-params (always allowed everywhere):

- `?cursor=` / `?limit=` — pagination (see [idempotency-pagination.md](idempotency-pagination.md))
- `?fields=` — sparse fieldsets
- `?include=` — eager-load related resources (`?include=line_items,customer`)
- `?expand=` — synonym; pick one project-wide

### Action Endpoints When Resources Don't Fit

For operations that aren't naturally CRUD on a noun, use a `/{resource}/{id}/actions/{verb}` pattern. Sparingly.

```
POST /orders/{id}/actions/cancel        # cancel an order
POST /payments/{id}/actions/refund       # refund a payment
POST /lessons/{id}/actions/start         # mark lesson started
```

Body carries action-specific data (reason, amount). Returns updated resource.

## HTTP Methods — Idempotency + Safety Matrix

| Method | Safe (no side effects) | Idempotent (same result on retry) | Body |
|---|---|---|---|
| GET | ✓ | ✓ | no |
| HEAD | ✓ | ✓ | no |
| OPTIONS | ✓ | ✓ | no |
| PUT | ✗ | ✓ | yes |
| DELETE | ✗ | ✓ | rare |
| PATCH | ✗ | ✗ (depends) | yes |
| POST | ✗ | ✗ | yes |

**Rules**:

- `GET` MUST NOT mutate state. Cachers, browsers, prefetchers will retry it.
- `PUT` replaces the entire resource. Same payload twice → same end state.
- `PATCH` modifies fields. Most natural updates. **Not idempotent by default** (consider `Idempotency-Key`).
- `DELETE` is idempotent — second `DELETE` on a deleted resource → 204 (or 404; document which).
- `POST` is the catch-all for "create" or "non-idempotent action". ALWAYS pair with `Idempotency-Key`.

## Status Codes — Authoritative Reference

### 2xx Success

- **200 OK** — Standard success with body. GET, PATCH, POST that returns existing resource.
- **201 Created** — POST that created a resource. MUST include `Location: /orders/{new_id}` header.
- **202 Accepted** — Async work queued. Body should describe how to poll status.
- **204 No Content** — DELETE success, idempotent PUT with no useful response. NO body.

### 3xx Redirects (rare in JSON APIs)

- **301 Moved Permanently** — URL renamed; clients should update.
- **304 Not Modified** — Conditional GET (`If-None-Match`/`If-Modified-Since`) hit cached version.

### 4xx Client Errors

- **400 Bad Request** — Malformed syntax, missing required field, type mismatch.
- **401 Unauthorized** — No credentials or invalid credentials. Include `WWW-Authenticate` header.
- **403 Forbidden** — Authenticated but lacks permission for THIS resource.
- **404 Not Found** — Resource doesn't exist OR you want to hide its existence from this caller.
- **405 Method Not Allowed** — POST to a GET-only URL. Include `Allow: GET, HEAD` header.
- **409 Conflict** — Duplicate, lost-update, state-machine violation ("can't cancel a shipped order").
- **410 Gone** — Resource was here, deliberately deleted. Used when 404 would be misleading.
- **412 Precondition Failed** — `If-Match` ETag mismatch. Optimistic concurrency.
- **413 Payload Too Large** — Body over limit.
- **415 Unsupported Media Type** — Wrong `Content-Type`.
- **422 Unprocessable Entity** — Syntactically valid, semantically invalid (business rule violation).
- **429 Too Many Requests** — Rate limit hit. MUST include `Retry-After`.

### 5xx Server Errors

- **500 Internal Server Error** — Unhandled exception. Should be rare; if it isn't, fix.
- **502 Bad Gateway** — Upstream service returned garbage.
- **503 Service Unavailable** — Temporarily down (maintenance, overload). Include `Retry-After` if known.
- **504 Gateway Timeout** — Upstream timed out.

### Codes to Avoid

- **418 I'm a Teapot** — Cute. Don't.
- **422 vs 400** — Be consistent project-wide. We use 400 for syntax, 422 for business rules.
- **451 Unavailable for Legal Reasons** — Real, but use sparingly and don't leak which jurisdiction.

## Request Bodies

### Always JSON, Always Validated

```http
POST /orders
Content-Type: application/json
Idempotency-Key: 8e0f7b1d-2a44-4c7f-9b2e-1c5d6e7f8a9b

{
  "user_id": "usr_abc123",
  "items": [
    { "sku": "BOOK-1", "quantity": 2 },
    { "sku": "PEN-3",  "quantity": 5 }
  ],
  "promo_code": "WELCOME10"
}
```

Validation rules:

1. **Reject unknown fields** by default (`additionalProperties: false` in JSON schema). Catches typos at the wire.
2. **Validate at the boundary**, not at the use case. Pydantic in FastAPI; struct tags + `go-playground/validator` in Fiber.
3. **Coerce types intentionally**. `"quantity": "2"` → reject 400, do NOT silently coerce string→int.
4. **Limit body size** at the framework. 1MB default; raise per-endpoint if needed.

### Field Naming — `snake_case` for JSON

Industry split is real (`camelCase` is also common). For this project, use `snake_case` because Python and Postgres both speak snake natively, and the Go side translates with `json:"user_id"` tags. RN client uses a small camelCase-converter at the boundary.

```typescript
// On the client, convert at the boundary:
import { camelizeKeys, decamelizeKeys } from 'humps';
const apiOrder = await fetch('/orders').then(r => r.json());
const order = camelizeKeys(apiOrder);  // { userId, ... }
```

### Date / Time — RFC 3339, Always UTC

```
✓ "2026-04-26T14:30:00Z"
✓ "2026-04-26T14:30:00.123Z"
✗ "2026-04-26 14:30:00"      # missing T separator
✗ "2026/04/26"               # use ISO
✗ 1745678900                 # epoch ints — fine for internal, no for public
```

### Money — Integer Cents, Currency Field

```json
{ "amount": 4200, "currency": "USD" }     // $42.00
```

Never floats. Never decimal strings unless you have a documented Decimal type. Always include currency.

### IDs — Prefixed, Opaque, URL-safe

```
✓ "ord_8h2k4n9d3p7q"     # type prefix + base32/base58
✓ "usr_aaaa1234bbbb"
✗ 4271                    # raw int — leaks count, predictable
✗ "550e8400-e29b-41d4..." # raw UUID — fine, but no type info at-a-glance
```

Prefixes (Stripe-style): `ord_`, `usr_`, `pay_`, `lsn_`, `prd_`. Reserve 3–4 chars + underscore.

## Response Shapes

### Single Resource

```json
{
  "id": "ord_8h2k4n9d3p7q",
  "status": "paid",
  "total": 4200,
  "currency": "USD",
  "created_at": "2026-04-26T14:30:00Z",
  "items": [...]
}
```

Bare object. No top-level `data` envelope unless you commit to it everywhere.

### Collection

```json
{
  "data": [
    { "id": "ord_a", ... },
    { "id": "ord_b", ... }
  ],
  "page": {
    "next_cursor": "eyJpZCI6Im9yZF9iIn0",
    "has_more": true
  }
}
```

The `data` envelope is mandatory for collections (room for pagination metadata). Single resources stay bare; consistency is per-shape, not per-endpoint.

### Empty Collection

```json
{ "data": [], "page": { "next_cursor": null, "has_more": false } }
```

Never `null`, never 404 for "no results". Empty list is a valid result.

## Cache Headers

```http
HTTP/1.1 200 OK
Cache-Control: public, max-age=300
ETag: "8h2k4n9d3p7q-v3"
Last-Modified: Sat, 26 Apr 2026 14:30:00 GMT
Vary: Accept, Accept-Encoding
```

Rules:

- **Authenticated endpoints**: `Cache-Control: private, max-age=N` or `no-store` for sensitive.
- **Public endpoints**: `Cache-Control: public, max-age=N` to enable CDN.
- **ETag** for any resource that supports conditional GET. Use weak ETags (`W/"..."`) when computing strong is too expensive.
- **`Vary`** correctly — auth headers, accept-language, etc.

## Common REST Anti-Patterns

1. **Putting verbs in URLs**. `POST /createOrder` → use `POST /orders`.
2. **Tunneling reads through POST**. Even "complex queries" can use GET with query params or POST with explicit `/search` endpoint.
3. **One endpoint that does many things**. `POST /orders` that creates OR updates depending on body shape — split into POST + PATCH.
4. **Inconsistent error response shape**. Some endpoints return `{"error": "..."}`, others return `{"errors": [...]}`. Pick one envelope.
5. **Returning 200 with `{"success": false}`**. Use the right HTTP status.
6. **HTTP error embedded in 2xx body**. Same.
7. **List endpoints without pagination**. Works in dev, OOMs at scale.
8. **Mutations without `Idempotency-Key`**. Network retries become double charges.
9. **Different field naming per endpoint**. `userId` here, `user_id` there. Pick one.
10. **Never marking deprecated fields**. Add `Deprecation` header (RFC 9745) when you decide to remove a field; give 6 months warning.
11. **`null` vs missing field with different semantics, undocumented**. Explicitly state in spec.
12. **Returning database error messages**. `"duplicate key violates unique constraint users_email_key"` leaks schema. Map to `code: "email_taken"`.
13. **No request size limit**. Frameworks default to 1MB; document and tune per endpoint.
14. **Synchronous endpoints that can take minutes**. Use 202 + polling pattern.
15. **Sparse fieldsets that bypass authorization**. `?fields=internal_notes` must still respect ACL.

## Concrete: Fiber Handler with All the Right Pieces

```go
// internal/adapter/http/order_handler.go
package http

import (
    "errors"

    "github.com/gofiber/fiber/v3"
    "myapp/internal/app/usecase"
    "myapp/internal/domain/order"
    "myapp/pkg/apperr"
)

func (h *OrderHandler) Create(c fiber.Ctx) error {
    // 1. Idempotency key (mandatory for mutating endpoints).
    idemKey := c.Get("Idempotency-Key")
    if idemKey == "" {
        return apperr.BadRequest(c, "missing_idempotency_key",
            errors.New("Idempotency-Key header is required"))
    }
    if cached, hit := h.idemStore.Lookup(c.Context(), idemKey); hit {
        return c.Status(cached.Status).Set("X-Idempotent-Replay", "true").Send(cached.Body)
    }

    // 2. Parse + validate.
    var req createOrderRequest
    if err := c.Bind().JSON(&req); err != nil {
        return apperr.BadRequest(c, "invalid_payload", err)
    }
    if err := req.Validate(); err != nil {
        return apperr.UnprocessableEntity(c, "validation_failed", err)
    }

    // 3. Translate to use case command (DTO at the boundary).
    cmd, err := req.toCommand()
    if err != nil {
        return apperr.UnprocessableEntity(c, "validation_failed", err)
    }

    // 4. Execute.
    out, err := h.placeOrder.Execute(c.Context(), cmd)
    if err != nil {
        return apperr.FromDomainError(c, err)  // maps to RFC 9457 envelope
    }

    // 5. Build response, set Location header, store idempotent result.
    body := newOrderResponse(out)
    c.Set("Location", "/orders/"+out.OrderID.String())
    h.idemStore.Store(c.Context(), idemKey, 201, body)

    return c.Status(201).JSON(body)
}
```

## Concrete: FastAPI Endpoint with Pydantic Validation

```python
# src/ai_adapter/delivery/http/routers/conversation.py
from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

router = APIRouter(prefix="/conversations", tags=["conversation"])


class CreateConversationRequest(BaseModel):
    model_config = {"extra": "forbid"}  # reject unknown fields
    user_id: str = Field(min_length=4, max_length=64, pattern=r"^usr_[a-z0-9]+$")
    initial_prompt: str = Field(min_length=1, max_length=4000)


class CreateConversationResponse(BaseModel):
    id: str
    user_id: str
    created_at: str  # RFC 3339


@router.post("", response_model=CreateConversationResponse, status_code=201)
async def create_conversation(
    body: CreateConversationRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8),
    use_case = Depends(get_create_conversation),
) -> CreateConversationResponse:
    cached = await use_case.idempotent_lookup(idempotency_key)
    if cached:
        return cached

    try:
        result = await use_case.execute(
            CreateConversationInput(
                user_id=body.user_id,
                initial_prompt=body.initial_prompt,
            )
        )
    except UserNotFoundError as exc:
        # RFC 9457 envelope built by global exception handler.
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    response = CreateConversationResponse(
        id=result.conversation_id,
        user_id=result.user_id,
        created_at=result.created_at.isoformat() + "Z",
    )
    await use_case.idempotent_store(idempotency_key, response)
    return response
```

## OpenAPI Snippet — A Healthy Endpoint Spec

```yaml
paths:
  /orders:
    post:
      operationId: createOrder
      summary: Place a new order
      parameters:
        - $ref: '#/components/parameters/IdempotencyKey'
      requestBody:
        required: true
        content:
          application/json:
            schema: { $ref: '#/components/schemas/CreateOrderRequest' }
      responses:
        '201':
          description: Order created
          headers:
            Location:
              schema: { type: string }
              required: true
          content:
            application/json:
              schema: { $ref: '#/components/schemas/Order' }
        '400':
          $ref: '#/components/responses/BadRequest'
        '422':
          $ref: '#/components/responses/UnprocessableEntity'
        '429':
          $ref: '#/components/responses/RateLimited'
components:
  parameters:
    IdempotencyKey:
      name: Idempotency-Key
      in: header
      required: true
      schema: { type: string, minLength: 8, maxLength: 64 }
  responses:
    BadRequest:
      description: Malformed request
      content:
        application/problem+json:
          schema: { $ref: '#/components/schemas/ProblemDetails' }
```

## Tools

- **Spec lint**: `spectral lint openapi.yaml` — catches malformed spec, missing examples, broken refs.
- **Mock server**: `prism mock openapi.yaml` — frontend builds against this while backend implements.
- **Property-based contract tests**: `schemathesis run http://localhost:8080 --checks all` — generates payloads from spec, hits live server.
- **Codegen**: `oapi-codegen` (Go), `datamodel-code-generator` (Python), `openapi-typescript-codegen` (TS) — typed clients/handlers from one spec.
- **Diff**: `oasdiff` — automated breaking-change detection in CI.
