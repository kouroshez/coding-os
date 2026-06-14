<!-- domain:BACKEND | layer:rules | ssot:true | updated:{{DATE}} -->
# Spring Boot Engineering Rules

Purpose: Non-negotiable conventions for the {{PROJECT_NAME}} Spring Boot backend.
Read when: Editing anything under `src/backend/`.
Skip when: Frontend/mobile work.
Read next: [Spring Boot Service Playbook](../playbooks/spring-boot-service.md)

> Nav: [Master Index](../00-index.md)

## Hard rules

1. **Layering** — `@RestController` → `@Service` → `@Repository`, imports flow one
   way only (the table in the `spring-boot` skill is the SSOT).
2. **Transport-free services** — a `@Service` importing `HttpServletRequest` or
   building a response is a build-blocking review finding.
3. **One error shaper** — only the global `@RestControllerAdvice` writes error
   bodies; it logs full detail and returns the problem shape with no internals
   (no stack traces, no driver messages).
4. **Validation fail-closed** — every input is a `@Valid` Bean Validation DTO; an
   unvalidated `@RequestBody` never reaches a service.
5. **Dependency injection** — inject by constructor into `final` fields; never
   `new` a bean and never use field injection — both bypass the container and
   break test overrides.
6. **No floating config** — bind configuration once via `@ConfigurationProperties`
   types; services receive typed config, never read raw `Environment` keys deep in
   a method.
7. **Formatted + warning-clean** — `spotless:check` (Google Java Format) is the lint
   gate; a suppressed warning requires a written justification at the call site.

## Testing bar

Services ≥ unit-tested per public method (no context, mocked collaborators);
controllers ≥ happy + error path via `@SpringBootTest` + `MockMvc`; repositories
integration-tested with `@DataJpaTest` against a disposable database.
