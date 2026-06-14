---
name: spring-boot
tier: stack
domain: [backend]
description: Use when creating or modifying Java files under src/backend/ in a Spring Boot service — the @SpringBootApplication bootstrap, @RestController endpoints, @Service beans, Spring Data repositories, the global @RestControllerAdvice, @ConfigurationProperties, DTOs, and their tests. Triggers on any .java change under src/backend/. Covers constructor DI/bean wiring, thin controllers, the single error-shaping advice, fail-closed @Valid Bean Validation, the configuration-properties pattern, and slice/integration testing with @SpringBootTest + MockMvc. Also known as spring.
globs: "src/backend/**/*.java"
depends_on:
  - clean-code
  - backend-fundamentals
  - api-design
last_reviewed: "2026-06-14"
---

REQUIRED BACKGROUND: You MUST also follow the core `clean-code` and
`backend-fundamentals` skills. This skill adds Spring Boot-specific patterns on
top.

# spring-boot

## Layer contract (matches `structure.tree`)

| Layer | May import | Never |
|---|---|---|
| `*Controller.java` (`@RestController`) | the feature service, DTOs | repositories, other controllers |
| `*Service.java` (`@Service`) | repositories, other services | `HttpServletRequest`/`ServletResponse`, transport types |
| `*Repository.java` (`@Repository`) | the `EntityManager` / Spring Data | services, controllers |
| `common/` (advice/filters) | services (for auth lookups) | repositories |

Services stay transport-free — no `HttpServletRequest` — so they are
unit-testable and a transport swap (Spring MVC → WebFlux → messaging listener) is
a controller-layer-only change.

## DI & wiring

- Inject collaborators by constructor into `final` fields; never `new` a bean and
  never use field injection (`@Autowired` on a field) — both bypass the container
  and break test overrides.
- `@SpringBootApplication` owns wiring only, not business logic. Component scanning
  discovers `@RestController`/`@Service`/`@Repository` beans in the base package
  and below — there is no manual registration step.
- Bean scopes: the default singleton for stateless services/repositories; only
  reach for `@Scope("prototype")`/request scope when state genuinely demands it. A
  singleton holding mutable request state is a bug.
- Keep the bootstrap class reachable so `@SpringBootTest` builds the context
  without binding a real port (`webEnvironment = RANDOM_PORT` or `MOCK`).

## Controllers (thin)

- A handler binds/validates the `@Valid` DTO → calls ONE service method → returns
  the value (Spring serializes). Do not build the response envelope by hand;
  return a typed record or `ResponseEntity<T>` when you need to set status/headers.
- No try/catch for error shaping in a controller — throw a typed exception (a
  domain exception or `ResponseStatusException`) and let the global advice shape it.

## Validation

- Every body/path/query input is a Bean Validation DTO behind `@Valid`
  (`jakarta.validation` constraints); reject fail-closed before the service runs.
  The service receives a typed, validated value and never reads the raw request.

## Error handling

- ONE global `@RestControllerAdvice` (`common/GlobalExceptionHandler.java`) shapes
  every error response (RFC 9457 problem shape via `ProblemDetail`, per
  `docs/api-contracts/error-format.md`). Unknown exceptions → 500 generic message,
  full detail to the logger only — never a stack trace to the client.
- Map typed domain exceptions to their status in dedicated `@ExceptionHandler`
  methods on the same advice; keep the catch-all `Exception.class` last.

## Configuration

- Bind configuration once via `@ConfigurationProperties` types; services receive
  typed config objects and never read raw `Environment`/`@Value` keys deep in a
  method.

## Testing

- Services: pure unit tests, no context — construct with Mockito fakes/mocks and
  assert.
- Controllers/integration: `@SpringBootTest` + `MockMvc` (or `@WebMvcTest` for a
  controller slice) builds the app in-memory; one happy + one error-path per
  endpoint minimum.
- Repositories: `@DataJpaTest` against a disposable database.
- Never bind a real port in tests; always build through the test context.
