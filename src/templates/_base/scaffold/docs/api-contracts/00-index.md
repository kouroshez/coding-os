<!-- domain:API | layer:index | ssot:true | updated:{{DATE}} -->
# API Contracts — Index

Purpose: Navigation hub for API contract documentation (request/response shapes, error codes, auth requirements).
Read when: Implementing or consuming an API endpoint, or aligning frontend types with backend.
Skip when: The task is purely internal logic with no API surface.
Read next: The specific endpoint contract file relevant to your task.

> Nav: [Docs Index](../00-index.md)

## Files

- [Error Format](./error-format.md) — Universal error envelope and codes
<!-- Add as APIs are documented:
- [Auth Endpoints](./auth-endpoints.md)
- [Catalog Endpoints](./catalog-endpoints.md)
-->

## Format

Each endpoint contract follows this structure:

```markdown
## POST /api/v1/<resource>

### Request

| Field | Type | Required | Notes |
|---|---|---|---|
| ... | ... | ... | ... |

### Response (2xx)

```json
{ ... }
```

### Errors

| Status | Code | When |
|---|---|---|
| 400 | VALIDATION_ERROR | Invalid input |
| 401 | UNAUTHORIZED | Missing/invalid auth |
| 403 | FORBIDDEN | Insufficient permissions |
| 404 | NOT_FOUND | Resource missing |

### Auth

Required scope: `...`
```

## Authoring Rules

- One file per resource group (auth, catalog, orders, etc.).
- Document both request and response in full — the contract is the SSOT.
- All errors follow `error-format.md`.
- When OpenAPI/Swagger is generated from code, link to the spec file but keep this human-readable doc up to date.
- Breaking changes require an ADR (`../architecture/adr/`) and a versioned endpoint path.
