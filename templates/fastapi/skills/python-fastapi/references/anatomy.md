<!-- domain:FASTAPI | layer:reference | ssot:true | updated:2026-04-29 -->
# FastAPI Anatomy

> P: Canonical file map and entity recipes for the FastAPI + Pydantic stack.
> R: Adding any `.py` under `backend/`, or routing a backend-API task.
> S: Working on frontend / mobile / web code.
> N: [SKILL.md](../SKILL.md), [scaffold-boundary.yaml](../../../scaffold-boundary.yaml)

> Nav: [Skill](../SKILL.md)

---

## 1. Boundary

SSOT: [`templates/fastapi/scaffold-boundary.yaml`](../../../scaffold-boundary.yaml).

## 2. Layout map

| Pattern | Location | Naming | Imports from | Description |
|---|---|---|---|---|
| App entry | `backend/main.py` | `main.py` (literal) | `.api`, `.core` | Mounts FastAPI() |
| Router | `backend/api/<resource>.py` | `<resource>.py` | `..schemas`, `..services` | APIRouter group |
| Schema (Pydantic) | `backend/schemas/<entity>.py` | `<entity>.py` | none cross-area | Request / response models |
| Service | `backend/services/<name>.py` | `<name>.py` | `..repositories` | Business logic, no HTTP |
| Repository | `backend/repositories/<name>.py` | `<name>.py` | `..db.models` | DB access only |
| ORM model | `backend/db/models/<entity>.py` | `<entity>.py` | `..base` | SQLAlchemy declarative |
| DB session | `backend/db/session.py` | `session.py` (literal) | `sqlalchemy` | Engine + session factory |
| Migration (Alembic) | `backend/db/migrations/versions/<rev>_<slug>.py` | autogen | `alembic.op` | Schema change |
| Dependency | `backend/api/deps.py` | `deps.py` (literal) | `..services` | FastAPI Depends |
| Config | `backend/core/config.py` | `config.py` (literal) | `pydantic_settings` | Settings model |
| Test | `backend/tests/test_<name>.py` | `test_<name>.py` | source under test | pytest + httpx.AsyncClient |

## 3. Entity recipes

### Add a new endpoint

- **Trigger:** "add POST /api/users", "expose endpoint X".
- **Files:**
  1. `backend/api/<resource>.py` (extend or create router)
  2. `backend/schemas/<entity>.py`
  3. `backend/services/<name>.py` (if business logic)
  4. `backend/tests/test_<resource>_api.py`
- **Steps:**
  1. Define Pydantic schema for request + response.
  2. Use `Depends()` for auth + db session — never instantiate inside the handler.
  3. Call into `services/` — never query the DB inside the route function.
  4. Set `response_model`, `status_code`, and OpenAPI tags explicitly.
  5. Test happy + 422 + 401 + 404 paths via `httpx.AsyncClient`.
- **Generator:** [`scripts/new_endpoint.py`](../scripts/new_endpoint.py).

### Add a new model

- **Trigger:** "add User model", "new SQLAlchemy entity".
- **Files:**
  1. `backend/db/models/<entity>.py`
  2. `backend/db/migrations/versions/<rev>_<slug>.py` (via `alembic revision --autogenerate`)
  3. `backend/repositories/<name>.py`
  4. `backend/tests/test_<entity>_model.py`
- **Steps:**
  1. Inherit from a project base (UUID PK, timestamps).
  2. Add indexes via `__table_args__`.
  3. Generate migration; review generated SQL before commit.
  4. Repository encapsulates queries — no raw SQL outside.

### Add a new service

- **Trigger:** "extract route logic", "share business logic".
- **Files:**
  1. `backend/services/<name>.py`
  2. `backend/tests/test_<name>_service.py`
- **Steps:**
  1. Pure async functions on top of repositories.
  2. Raise typed exceptions; routers map to HTTPException.
  3. Mock the repository in tests — no DB I/O at the service layer test.

### Add a new migration

- **Trigger:** schema change.
- **Files:**
  1. `backend/db/migrations/versions/<rev>_<slug>.py`
- **Steps:**
  1. Append-only — never edit a merged revision.
  2. Data migrations include both `upgrade()` and `downgrade()`.
  3. Test on a staging DB with prod-shaped data before merge.

### Add a new test

- **Trigger:** any new endpoint / model / service requires tests.
- **Files:**
  1. `backend/tests/test_<name>.py`
- **Steps:**
  1. pytest + `httpx.AsyncClient(app=app)` for endpoints.
  2. Given/When/Then; cover happy + at least one failure path.
  3. Real DB inside (test DB), mocks at external boundaries (HTTP, email).

## 4. Conventions

#### Naming

- Files / packages: `snake_case`.
- Classes (Pydantic / ORM): `PascalCase`.
- Functions / variables: `snake_case`.
- Constants: `SCREAMING_SNAKE_CASE`.
- Tests: `test_<thing>.py` under `backend/tests/`.

#### Test colocation

Mirrored. Tests live under `backend/tests/test_<name>.py` — never colocated next to source. Reason: pytest discovery + shared fixtures (`conftest.py`).

#### Dependency rules

- ✓ `backend/api/` may import from `backend/services/` and `backend/schemas/`.
- ✓ `backend/services/` may import from `backend/repositories/` and `backend/schemas/`.
- ✓ `backend/repositories/` may import from `backend/db/`.
- ✗ Routers may NOT touch DB models directly — go through services + repositories.
- ✗ Schemas may NOT import services or repositories.
- ✗ `backend/` may NOT import from `frontend/`, `mobile/`, `ai-service/`.
