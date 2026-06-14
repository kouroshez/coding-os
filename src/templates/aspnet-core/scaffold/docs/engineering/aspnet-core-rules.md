<!-- domain:BACKEND | layer:rules | ssot:true | updated:{{DATE}} -->
# ASP.NET Core Engineering Rules

Purpose: Non-negotiable conventions for the {{PROJECT_NAME}} ASP.NET Core backend.
Read when: Editing anything under `src/backend/`.
Skip when: Frontend/mobile work.
Read next: [ASP.NET Core Service Playbook](../playbooks/aspnet-core-service.md)

> Nav: [Master Index](../00-index.md)

## Hard rules

1. **Layering** — endpoint → service → repository, imports flow one way only
   (the table in the `aspnet-core` skill is the SSOT).
2. **Transport-free services** — a service importing `HttpContext` or building a
   response is a build-blocking review finding.
3. **One error shaper** — only the global `ExceptionHandlingMiddleware` writes
   error bodies; it logs full detail and returns the problem shape with no
   internals (no stack traces, no driver messages).
4. **Validation fail-closed** — every input is a validated DTO; an unvalidated
   body never reaches a service.
5. **Dependency injection** — register services in `Program.cs` and inject by
   constructor / endpoint parameter; never `new` a service — it bypasses the
   container and breaks test overrides.
6. **Nullable + warnings-as-errors** — `<Nullable>enable</Nullable>` and
   `TreatWarningsAsErrors` are the lint gate; a `!` null-forgiving operator
   requires a written justification at the call site.
7. **No floating config** — bind configuration once at bootstrap via the options
   pattern (`IOptions<T>`); services receive typed options, never read raw
   configuration keys.

## Testing bar

Services ≥ unit-tested per public method (no host); endpoints ≥ happy + error
path via `WebApplicationFactory<Program>`; repositories integration-tested
against a disposable database.
