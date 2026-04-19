# FastAPI Service Playbook

Project: {{PROJECT_NAME}} · Stack: {{STACK}} · Updated: {{DATE}}

## When to use

Use this playbook for any task that creates, modifies, or debugs FastAPI routes,
Pydantic schemas, SQLAlchemy models, or backend services under `backend/`.

## Always read

1. `docs/engineering/fastapi-rules.md` — canonical backend policy
2. `docs/playbooks/security-review.md` — for any auth / data-access code path
3. This file — routing and file-layout conventions

## Task-to-file mapping

| Task type | Files to read first |
|---|---|
| New route | `backend/app/api/v1/<resource>.py`, related schema + service |
| Schema change | `backend/app/models/<model>.py`, `backend/app/schemas/<schema>.py`, alembic migrations |
| New service | `backend/app/services/<domain>.py`, related repository |
| Auth / permissions | `backend/app/deps.py`, `backend/app/core/security.py` |

## Execution rules

1. Route layer never touches the DB directly — always via a service function.
2. Every new route gets a unit test for the happy path and at least one error path.
3. Migrations must be reversible. Never edit an applied migration.
4. Run `make verify-backend` before marking task-done.
