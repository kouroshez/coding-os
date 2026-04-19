---
name: python-fastapi
description: Use when creating or modifying Python files under backend/ — FastAPI routes, Pydantic models, SQLAlchemy ORM, dependency-injected services, async handlers, and pytest tests. Triggers on any .py file change under backend/. Covers route organization, dependency injection, error handling, and async patterns specific to FastAPI.
globs: "backend/**/*.py"
depends_on:
  - clean-code
  - backend-fundamentals
---

REQUIRED BACKGROUND: You MUST also follow the clean-code skill (`.claude/skills/clean-code/SKILL.md`). That skill covers universal principles (fail-closed errors, typed exceptions, self-documenting code, edge cases, error path tests). This skill adds FastAPI-specific patterns on top of those foundations.

## Pre-Code Checklist

Before writing any backend Python code, verify:

- [ ] Read `docs/engineering/fastapi-rules.md` — the canonical backend policy
- [ ] If touching API routes: read `docs/playbooks/fastapi-service.md`
- [ ] Search the repo with Grep/Glob for existing code before creating any new file
- [ ] Confirm which Python version the project targets (≥ 3.11 recommended)

## 1. Project layout

```
backend/
├── app/
│   ├── main.py              # FastAPI() entry point
│   ├── api/                 # route modules, one file per resource
│   │   └── v1/
│   ├── models/              # SQLAlchemy declarative models
│   ├── schemas/             # Pydantic request/response schemas
│   ├── services/            # business logic — pure, no Request/Response types
│   ├── deps.py              # dependency providers (DB session, current user)
│   └── core/
│       ├── config.py        # Pydantic Settings
│       └── exceptions.py    # typed domain errors
└── tests/
```

## 2. Route pattern

```python
@router.post("/items", response_model=ItemOut, status_code=201)
async def create_item(
    payload: ItemIn,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> ItemOut:
    item = await items_service.create(session, payload, owner=current_user)
    return ItemOut.model_validate(item)
```

- Route layer: validation, auth, serialization. No DB queries.
- Service layer: business logic, pure functions on top of repositories.
- Models ≠ schemas. Never return SQLAlchemy objects directly.

## 3. Error handling

- Define domain exceptions in `app/core/exceptions.py` (e.g., `NotFoundError`, `PermissionDenied`).
- Register a single exception handler in `main.py` that maps them to HTTP responses with a consistent envelope.
- Never return `{"error": str(e)}` — always a structured shape.

## 4. Async discipline

- Use `AsyncSession` + `async def` end-to-end. Mixing sync and async breaks the event loop.
- I/O-bound work only. For CPU-bound work, offload to a task queue.

## 5. Testing

- `httpx.AsyncClient` + `pytest-asyncio` for endpoint tests.
- Use a transactional fixture that rolls back after each test.
- Target ≥ 80% coverage. Test error paths explicitly.
