<!-- domain:ASPNETCORE | layer:reference | ssot:true | updated:2026-06-27 -->
# ASP.NET Core Anatomy

> P: Canonical file map + entity recipes for the ASP.NET Core (minimal-API, feature-folder) stack.
> R: Adding any `.cs`/`.csproj` under `src/backend/`, or routing a backend task.
> S: Reading frontend / mobile code — wrong stack.
> N: [SKILL.md](../SKILL.md), [scaffold-boundary.yaml](../../../scaffold-boundary.yaml)

> Nav: [Skill](../SKILL.md)

---

## 1. Boundary

SSOT: `src/templates/aspnet-core/scaffold-boundary.yaml`.

## 2. Layout map

| Pattern | Location | Naming | Imports from | Description |
|---|---|---|---|---|
| Endpoints | `Features/<Feature>/<Feature>Endpoints.cs` | `<Feature>Endpoints.cs` | its service | Thin — maps routes, delegates to the service |
| Service | `Features/<Feature>/<Feature>Service.cs` | `<Feature>Service.cs` | repository | Business logic (the only layer that thinks) |
| DTO | `Features/<Feature>/<Feature>Dtos.cs` | `<Feature>Dtos.cs` | none | Request / response records + validation attrs |
| Middleware | `Common/ExceptionHandlingMiddleware.cs` | `<Name>Middleware.cs` | none | The ONLY error-response shaper (ProblemDetails) |
| Bootstrap | `Program.cs` | `Program.cs` | Features | `WebApplication` wiring — no business logic |
| Test | `tests/<Feature>Tests.cs` | `<Feature>Tests.cs` | source under test | xUnit |

## 3. Entity recipes

### Add a new endpoint
- **Trigger:** "add `POST /<feature>`", "expose endpoint X".
- **Files emitted:**
  1. `Features/<Feature>/<Feature>Endpoints.cs`
  2. `Features/<Feature>/<Feature>Service.cs`
  3. `Features/<Feature>/<Feature>Dtos.cs`
- **Steps:**
  1. Map the route group in `<Feature>Endpoints.cs`; inject the service.
  2. Validate the DTO before it reaches the service; return typed results.
  3. Register the service in `Program.cs` DI (`AddScoped`).

### Add a new model
- **Trigger:** "persist `<Entity>`".
- **Files emitted:** `Features/<Feature>/<Entity>.cs` (+ EF config).
- **Steps:**
  1. Plain record/class; map via the DbContext, never expose it as a DTO.

### Add a new test
- **Trigger:** any new endpoint / service.
- **Files emitted:** `tests/<Feature>Tests.cs`.
- **Steps:**
  1. `WebApplicationFactory` for endpoint tests; mock the repo for service tests.
  2. Cover happy + validation-failure paths.

## 4. Conventions

#### Naming
- Files / types: `PascalCase` (`OrderService.cs`). Locals: `camelCase`; constants: `PascalCase`.

#### Test colocation
- Mirrored: `tests/<Feature>Tests.cs` mirrors `Features/<Feature>/`.

#### Dependency rules
- ✓ endpoint → service → repository.
- ✗ never `new` a service — resolve via the built-in DI container.
- ✗ `src/backend/` never imports from `src/frontend/` / `src/mobile/` — share via `src/shared/`.
