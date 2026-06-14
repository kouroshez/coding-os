---
globs: ["src/backend/**/*.java"]
alwaysApply: false
---

# Spring Boot Backend Rules (auto-loaded on src/backend/**/*.java)

When editing any Java file under `src/backend/` in a Spring Boot project, follow these standards:

- **Controller signature** — `@RestController` handlers take the `@Valid` DTO + path/query params and return a typed value or `ResponseEntity<T>`. No response envelope built by hand.
- **Typed errors** — throw a typed exception (a domain exception or `ResponseStatusException`); a single `@RestControllerAdvice` maps it to the RFC 9457 problem shape `{type, title, status}`. Never write an error body anywhere else.
- **Validation** — annotate request DTOs with Bean Validation constraints and `@Valid` at the controller boundary; reject fail-closed with field-level details. No raw `@RequestBody` reaching a service unvalidated.
- **Dependency injection** — inject collaborators by constructor (`final` fields); never `new` a bean or use field injection. A `new SomeService()` bypasses the container and breaks test overrides.
- **Layering** — `@RestController` → `@Service` → `@Repository`. Controllers don't touch a repository or `EntityManager` directly — services do.
- **Transport-free services** — a `@Service` importing `HttpServletRequest`/`ServletResponse` or building a response is a build-blocking review finding.
- **Tests** — every endpoint gets a `@SpringBootTest` + `MockMvc` (or `WebTestClient`) test, happy + error paths; services get context-free unit tests with mocked collaborators.

Canonical policy: `docs/engineering/spring-boot-rules.md`
Playbook: `docs/playbooks/spring-boot-service.md`
Primary skill: `spring-boot`
