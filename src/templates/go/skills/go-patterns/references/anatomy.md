<!-- domain:GO | layer:reference | ssot:true | updated:2026-04-29 -->
# Go Anatomy

> P: Canonical file map and entity recipes for the Go (stdlib net/http) stack.
> R: Adding any `.go` file under `src/backend/` or `cmd/`, or routing a backend task.
> S: Working on frontend / mobile / web code.
> N: [SKILL.md](../SKILL.md), [scaffold-boundary.yaml](../../../scaffold-boundary.yaml)

> Nav: [Skill](../SKILL.md)

---

## 1. Boundary

SSOT: [`src/templates/go/scaffold-boundary.yaml`](../../../scaffold-boundary.yaml).

## 2. Layout map

| Pattern | Location | Naming | Imports from | Description |
|---|---|---|---|---|
| App entry | `cmd/<service>/main.go` | `main.go` | `internal/...` | Wires deps, starts server |
| HTTP handler | `internal/<domain>/handler.go` | `handler.go` | `..service` | net/http handler |
| Service | `internal/<domain>/service.go` | `service.go` | `..repo` | Business logic |
| Repository | `internal/<domain>/repo.go` | `repo.go` | `database/sql` | DB access |
| Domain entity | `internal/<domain>/<entity>.go` | `<entity>.go` | `time` | Plain struct + methods |
| DTO | `internal/<domain>/dto.go` | `dto.go` | `encoding/json` | Wire format |
| Errors | `internal/<domain>/errors.go` | `errors.go` | none | Sentinel + wrap helpers |
| Migration | `migrations/<rev>_<slug>.up.sql` | `<rev>_<slug>.up.sql` | none | golang-migrate format |
| Config | `internal/config/config.go` | `config.go` | `os`, `flag` | env / flag binding |
| Test | `internal/<domain>/<file>_test.go` | `<file>_test.go` | source under test | Table-driven |
| Integration test | `internal/<domain>/integration_test.go` | tagged `//go:build integration` | testcontainers | Real DB |

## 3. Entity recipes

### Add a new HTTP handler

- **Trigger:** "add POST /api/users", "expose endpoint X".
- **Files:**
  1. `internal/<domain>/handler.go` (extend or create)
  2. `internal/<domain>/dto.go`
  3. `internal/<domain>/handler_test.go`
- **Steps:**
  1. Handler returns `http.HandlerFunc` constructed via constructor that takes the service.
  2. Decode request → DTO; validate via tags (`go-playground/validator`).
  3. Call into service; map sentinel errors to status codes via a single helper.
  4. Test with `httptest.NewRecorder` + table-driven cases.
- **Generator:** [`src/scripts/new_endpoint.py`](../scripts/new_endpoint.py).

### Add a new service

- **Trigger:** "extract logic", "share business rule".
- **Files:**
  1. `internal/<domain>/service.go`
  2. `internal/<domain>/service_test.go`
- **Steps:**
  1. Service is a struct with a constructor `NewService(repo Repo) *Service`.
  2. Methods take `context.Context` first.
  3. Errors wrapped with `fmt.Errorf("...: %w", err)` so callers can `errors.Is`.
  4. Test mocks the repo via interface; never hit the DB at service test level.

### Add a new repository

- **Trigger:** "persist X", "query Y from DB".
- **Files:**
  1. `internal/<domain>/repo.go`
  2. `internal/<domain>/repo_test.go` (or `integration_test.go`)
- **Steps:**
  1. Repo is a struct with `*sql.DB` (or `pgxpool.Pool`).
  2. All queries are constants at package scope; no string interpolation.
  3. Errors map to sentinels (`ErrNotFound`, `ErrConflict`).
  4. Integration tests use testcontainers + the real driver.

### Add a new migration

- **Trigger:** schema change.
- **Files:**
  1. `migrations/<rev>_<slug>.up.sql`
  2. `migrations/<rev>_<slug>.down.sql`
- **Steps:**
  1. Append-only — never edit a merged migration.
  2. Both up + down required; up must be reversible by down on a copy of prod.
  3. Data migrations carry their reverse explicitly.

### Add a new test

- **Trigger:** any new handler / service / repo requires tests.
- **Files:**
  1. `<source>_test.go` next to source.
- **Steps:**
  1. Table-driven; one struct slice per test function.
  2. Sub-tests via `t.Run(tt.name, …)`; parallel where safe.
  3. Race detector on CI: `go test -race ./...`.

## 4. Conventions

#### Naming

- Files: `snake_case.go` (Go convention).
- Packages: `lowercase`, no underscores.
- Exported symbols: `PascalCase`.
- Unexported symbols: `camelCase`.
- Interfaces named for the role (`Reader`, `Repo`), not the implementation.

#### Test colocation

Colocated. `service.go` ⇄ `service_test.go` in the same package. Integration tests carry the `//go:build integration` tag. No mirror dirs.

#### Dependency rules

- ✓ `cmd/` may import from `internal/`.
- ✓ `internal/<domain>/handler.go` may import from `internal/<domain>/service.go`.
- ✓ `internal/<domain>/service.go` may import from `internal/<domain>/repo.go`.
- ✗ Repos may NOT import from services or handlers.
- ✗ Domains may NOT import from sibling domain `internal/` packages — go through `internal/contracts/` if cross-domain coupling is unavoidable.
- ✗ `src/backend/` may NOT import from `src/frontend/`, `src/mobile/`, `src/ai-service/`.
