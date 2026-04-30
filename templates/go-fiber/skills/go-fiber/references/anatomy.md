<!-- domain:GOFIBER | layer:reference | ssot:true | updated:2026-04-29 -->
# Go + Fiber Anatomy

> P: Canonical file map and entity recipes for the Go + Fiber v2 stack.
> R: Adding any `.go` file under `backend/` or `cmd/`, or routing a backend task.
> S: Working on frontend / mobile / web code.
> N: [SKILL.md](../SKILL.md), [scaffold-boundary.yaml](../../../scaffold-boundary.yaml)

> Nav: [Skill](../SKILL.md)

---

## 1. Boundary

SSOT: [`templates/go-fiber/scaffold-boundary.yaml`](../../../scaffold-boundary.yaml).

## 2. Layout map

| Pattern | Location | Naming | Imports from | Description |
|---|---|---|---|---|
| App entry | `cmd/<service>/main.go` | `main.go` | `internal/...` | Wires fiber.New() |
| Fiber handler | `internal/<domain>/handler.go` | `handler.go` | `..service` | `func(c *fiber.Ctx) error` |
| Middleware | `internal/middleware/<name>.go` | `<name>.go` | `fiber.Handler` | Auth, logging, etc. |
| Service | `internal/<domain>/service.go` | `service.go` | `..repo` | Business logic |
| Repository | `internal/<domain>/repo.go` | `repo.go` | `database/sql` | DB access |
| Domain entity | `internal/<domain>/<entity>.go` | `<entity>.go` | `time` | Plain struct + methods |
| DTO / Request | `internal/<domain>/dto.go` | `dto.go` | `validator` | Wire format + validation tags |
| Errors | `internal/<domain>/errors.go` | `errors.go` | none | Sentinel + wrap helpers |
| Migration | `migrations/<rev>_<slug>.up.sql` | `<rev>_<slug>.up.sql` | none | golang-migrate format |
| Config | `internal/config/config.go` | `config.go` | `os`, `flag` | env / flag binding |
| Test | `internal/<domain>/<file>_test.go` | `<file>_test.go` | source under test | Table-driven |
| Integration test | `internal/<domain>/integration_test.go` | tagged `//go:build integration` | testcontainers | Real DB |

## 3. Entity recipes

### Add a new Fiber handler

- **Trigger:** "add POST /api/users", "expose endpoint X".
- **Files:**
  1. `internal/<domain>/handler.go` (extend or create)
  2. `internal/<domain>/dto.go`
  3. `internal/<domain>/handler_test.go`
- **Steps:**
  1. Handler returns `fiber.Handler`; constructor takes the service.
  2. Bind body via `c.BodyParser(&req)`; validate via tags.
  3. Call into service; map sentinel errors to status codes via a single helper.
  4. Use `c.Status(code).JSON(envelope)` — never write raw bytes.
  5. Test with `app.Test(req)` + table-driven cases.
- **Generator:** [`scripts/new_endpoint.py`](../scripts/new_endpoint.py).

### Add a new middleware

- **Trigger:** "add auth middleware", "log every request".
- **Files:**
  1. `internal/middleware/<name>.go`
  2. `internal/middleware/<name>_test.go`
- **Steps:**
  1. Return `fiber.Handler`; pass dependencies via the constructor.
  2. Always call `c.Next()` on the success path; return `nil` only after Next.
  3. Recover panics where applicable (`c.Status(500).JSON(...)`).
  4. Test with a fake fiber app and table-driven cases.

### Add a new service

- **Trigger:** "extract logic", "share business rule".
- **Files:**
  1. `internal/<domain>/service.go`
  2. `internal/<domain>/service_test.go`
- **Steps:**
  1. Constructor `NewService(repo Repo) *Service`.
  2. Methods take `context.Context` first; pass `c.UserContext()` from handler.
  3. Wrap errors with `fmt.Errorf("...: %w", err)`.
  4. Mock the repo via interface in tests.

### Add a new migration

- **Trigger:** schema change.
- **Files:**
  1. `migrations/<rev>_<slug>.up.sql`
  2. `migrations/<rev>_<slug>.down.sql`
- **Steps:**
  1. Append-only — never edit a merged migration.
  2. Up must be reversible by down on a copy of prod.

### Add a new test

- **Trigger:** any new handler / middleware / service / repo requires tests.
- **Files:**
  1. `<source>_test.go` next to source.
- **Steps:**
  1. Table-driven; sub-tests via `t.Run(tt.name, …)`.
  2. `app.Test(req)` for HTTP-level; mock service for handler tests.
  3. Race detector on CI: `go test -race ./...`.

## 4. Conventions

#### Naming

- Files: `snake_case.go`.
- Packages: `lowercase`, no underscores.
- Exported symbols: `PascalCase`.
- Unexported symbols: `camelCase`.
- Interfaces named for the role (`Reader`, `Repo`).

#### Test colocation

Colocated. `service.go` ⇄ `service_test.go` in the same package. Integration tests carry `//go:build integration`. No mirror dirs.

#### Dependency rules

- ✓ `cmd/` may import from `internal/`.
- ✓ `internal/<domain>/handler.go` → `service.go` → `repo.go`.
- ✓ Middleware lives in `internal/middleware/` and may import from `internal/contracts/` only.
- ✗ Repos may NOT import from services or handlers.
- ✗ Domains may NOT import from sibling `internal/<other-domain>/` — go through `internal/contracts/`.
- ✗ `backend/` may NOT import from `frontend/`, `mobile/`, `ai-service/`.
