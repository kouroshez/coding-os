---
globs: ["src/backend/**/*.py"]
alwaysApply: false
---

# FastAPI Backend Rules (auto-loaded on src/backend/**/*.py)

When editing any Python file under `src/backend/`, follow these standards:

- **Thin routes, fat services** — routes in `app/api/v1/` only validate + serialize; business logic in `app/services/`.
- **Pydantic v2** — separate `…In` request and `…Out` response schemas. Never return SQLAlchemy models directly.
- **Async end-to-end** — `async def` + `AsyncSession`. No sync I/O in request handlers.
- **Domain exceptions** — raise from `app/core/exceptions.py`, mapped to HTTP responses by a single handler in `main.py`.
- **Reversible migrations** — every Alembic migration must have a working `downgrade`.

Canonical policy: `docs/engineering/fastapi-rules.md`
Playbook: `docs/playbooks/fastapi-service.md`
Primary skill: `python-fastapi`
