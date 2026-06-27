<!-- domain:SPRINGBOOT | layer:reference | ssot:true | updated:2026-06-27 -->
# Spring Boot Anatomy

> P: Canonical file map + entity recipes for the Spring Boot (feature-package, constructor-DI) stack.
> R: Adding any `.java` under `src/backend/`, or routing a backend task.
> S: Reading frontend / mobile code — wrong stack.
> N: [SKILL.md](../SKILL.md), [scaffold-boundary.yaml](../../../scaffold-boundary.yaml)

> Nav: [Skill](../SKILL.md)

---

## 1. Boundary

SSOT: `src/templates/spring-boot/scaffold-boundary.yaml`.

## 2. Layout map

| Pattern | Location | Naming | Imports from | Description |
|---|---|---|---|---|
| Controller | `<feature>/<Feature>Controller.java` | `<Feature>Controller.java` | its service | Thin — maps routes, delegates |
| Service | `<feature>/<Feature>Service.java` | `<Feature>Service.java` | repository | Business logic (the only layer that thinks) |
| Repository | `<feature>/<Feature>Repository.java` | `<Feature>Repository.java` | none | Spring Data persistence |
| DTO | `<feature>/<Feature>Dtos.java` | `<Feature>Dtos.java` | none | `@Valid` Bean-Validation request shape |
| Error shaper | `common/GlobalExceptionHandler.java` | — | none | `@RestControllerAdvice` — the ONLY shaper |
| Test | `src/test/java/.../<Feature>Test.java` | `<Feature>Test.java` | source under test | JUnit 5 |

## 3. Entity recipes

### Add a new endpoint
- **Trigger:** "add `POST /<feature>`".
- **Files emitted:**
  1. `<feature>/<Feature>Controller.java`
  2. `<feature>/<Feature>Service.java`
  3. `<feature>/<Feature>Dtos.java`
- **Steps:**
  1. Controller constructor-injects the service; `@Valid` the request DTO.
  2. Service does the work; throws typed exceptions the advice maps.

### Add a new model
- **Trigger:** "persist `<Entity>`".
- **Files emitted:** `<feature>/<Entity>.java` + `<Feature>Repository.java`.
- **Steps:**
  1. `@Entity` + a `JpaRepository`; never expose the entity as a DTO.

### Add a new test
- **Trigger:** any new controller / service.
- **Files emitted:** `src/test/java/.../<Feature>Test.java`.
- **Steps:**
  1. `@WebMvcTest` for controllers; plain JUnit + Mockito for services.

## 4. Conventions

#### Naming
- Files / types: `PascalCase.java`. Methods / fields: `camelCase`; constants: `UPPER_SNAKE`.

#### Test colocation
- Mirrored: `src/test/java/...` mirrors `src/main/java/...`.

#### Dependency rules
- ✓ controller → service → repository; inject via constructor.
- ✗ never `new` a bean; no business logic in a controller.
- ✗ `src/backend/` never imports from `src/frontend/` / `src/mobile/` — share via `src/shared/`.
