# FastAPI Engineering Rules

Project: {{PROJECT_NAME}} · Updated: {{DATE}}

## Architecture

- **Routes** (`app/api/v1/`): thin. Validation, auth, serialization only.
- **Services** (`app/services/`): business logic. Pure async functions. Accept
  domain types, return domain types. Never import FastAPI types.
- **Repositories** (`app/repositories/` — optional): data access. Wrap SQLAlchemy.
- **Schemas** (`app/schemas/`): Pydantic v2 models. Separate `…In` and `…Out`.
- **Models** (`app/models/`): SQLAlchemy declarative. Never exposed directly.

## Error handling

- Domain exceptions live in `app/core/exceptions.py`.
- A single exception handler in `main.py` maps them to HTTP responses with
  a consistent envelope: `{"error": {"code", "message", "details"}}`.
- Never return raw `str(exc)` to clients.

## Async discipline

- `async def` + `AsyncSession` everywhere on the request path.
- No `time.sleep`, no sync HTTP clients in request handlers.
- CPU-bound work → task queue.

## Testing

- `pytest` + `pytest-asyncio` + `httpx.AsyncClient`.
- Transactional DB fixture (rollback after each test).
- Coverage target: ≥ 80% with error paths exercised.

## Migrations

- Alembic. Autogenerate is a starting point, not a finish line — review.
- Every migration must be reversible.
- Never edit an applied migration — append a new one.
