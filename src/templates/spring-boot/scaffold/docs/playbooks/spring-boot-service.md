<!-- domain:BACKEND | layer:playbook | ssot:true | updated:{{DATE}} -->
# Spring Boot Service Playbook

Purpose: The end-to-end recipe for adding or changing a Spring Boot endpoint in {{PROJECT_NAME}}.
Read when: Any task that adds a controller, service, repository, DTO, or security config.
Skip when: Pure infra/devops work — see the deployment docs.
Read next: [Spring Boot Engineering Rules](../engineering/spring-boot-rules.md), [Error Format](../api-contracts/error-format.md)

> Nav: [Master Index](../00-index.md)

## Add an endpoint (the only sanctioned path)

1. **Contract first** — define the request/response DTOs as records with Bean
   Validation constraints; error cases use the shared problem format
   ([error-format](../api-contracts/error-format.md)).
2. **Feature package** — `src/main/java/com/example/app/<feature>/` holds the
   controller + service for one domain; nothing else reaches into it.
3. **Controller** — `<Feature>Controller.java`: `@RestController`, validate the
   `@Valid` DTO, call exactly one service method, return the value. No response
   envelope built by hand.
4. **Service** — `<Feature>Service.java`: `@Service`, business logic only, no
   `HttpServletRequest` and no transport types, typed domain exceptions on failure.
5. **Repository** — `<Feature>Repository.java` (Spring Data) for one aggregate;
   services never touch the `EntityManager` directly.
6. **Wire** — nothing to register by hand: component scanning discovers the
   beans; the container injects them by constructor.
7. **Test** — unit-test the service (no context) with mocked collaborators +
   `@SpringBootTest` + `MockMvc` integration-test the endpoint (happy + error path).
8. **Verify** — `cd src/backend && ./mvnw -q verify`.

## Global wiring (set once)

`@SpringBootApplication` boots the context; the single `@RestControllerAdvice`
(`common/GlobalExceptionHandler.java`) is auto-registered so every route inherits
one error shape. The global `@Valid` + Bean Validation rejects bad input before a
service runs.

## Anti-patterns

- Error JSON built inside a controller — the `@RestControllerAdvice` owns the shape.
- A service importing `HttpServletRequest`/`ServletResponse` — that layer must stay
  transport-free.
- `new SomeService()` or field injection instead of constructor injection —
  bypasses the container and breaks test overrides.
- An unvalidated `@RequestBody` reaching a service — every input is a `@Valid` DTO.
