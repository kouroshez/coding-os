<!-- domain:API | layer:spec | ssot:true | updated:{{DATE}} -->
# Error Format

Purpose: Canonical error envelope used by all API endpoints.
Read when: Implementing an endpoint, mapping errors in the frontend, or adding a new error code.
Skip when: The task is internal and does not return errors over the wire.
Read next: Specific endpoint contracts in `./` for per-endpoint error matrices.

> Nav: [API Index](./00-index.md)

## Envelope

All API errors return JSON with this shape:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Human-readable message safe to show end-users.",
    "details": {
      "field_name": ["Field-level error"]
    },
    "request_id": "req_abc123"
  }
}
```

### Field Rules

- `error.code` — UPPER_SNAKE_CASE machine-readable identifier. Stable across versions.
- `error.message` — Human-readable, localizable, never leaks internal details (SQL, stack, file paths).
- `error.details` — Optional. Field-level errors as `{field_name: [messages]}` or empty object.
- `error.request_id` — Correlation ID for log lookups. Always present.

## Standard Error Codes

| HTTP Status | Code | When |
|---|---|---|
| 400 | `VALIDATION_ERROR` | Input failed validation rules |
| 400 | `MALFORMED_REQUEST` | JSON parse failed, content-type wrong |
| 401 | `UNAUTHORIZED` | Missing or invalid credentials |
| 401 | `TOKEN_EXPIRED` | Auth token expired, refresh needed |
| 403 | `FORBIDDEN` | Authenticated but lacks permission |
| 404 | `NOT_FOUND` | Resource does not exist or hidden by ACL |
| 409 | `CONFLICT` | State conflict (e.g. duplicate, version mismatch) |
| 422 | `UNPROCESSABLE_ENTITY` | Semantically invalid (e.g. invalid state transition) |
| 429 | `RATE_LIMITED` | Too many requests, retry after `Retry-After` header |
| 500 | `INTERNAL_ERROR` | Unexpected server error. Generic message only. |
| 503 | `SERVICE_UNAVAILABLE` | Maintenance or downstream dependency failure |

## Authoring Rules

- Never leak SQL, stack traces, file paths, or internal variable names in `error.message`.
- Validation errors use `details` for field-level messages.
- New error codes require updating this table and any affected endpoint contracts.
- Backend raises typed exceptions; an exception handler maps them to this envelope.
- Frontend maps `error.code` to localized user messages, never displays raw `error.message` for `INTERNAL_ERROR`.
