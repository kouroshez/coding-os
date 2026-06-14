<!-- domain:BACKEND | layer:rules | ssot:true | updated:{{DATE}} -->
# NestJS Engineering Rules

Purpose: Non-negotiable conventions for the {{PROJECT_NAME}} NestJS backend.
Read when: Editing anything under `src/backend/`.
Skip when: Frontend/mobile work.
Read next: [NestJS Service Playbook](../playbooks/nestjs-service.md)

> Nav: [Master Index](../00-index.md)

## Hard rules

1. **Layering** — controller → provider → repository, imports flow one way only
   (the table in the `nestjs` skill is the SSOT).
2. **Transport-free providers** — a provider importing `@Req`/`@Res` or building
   a response is a build-blocking review finding.
3. **One error shaper** — only the global `AllExceptionsFilter` writes error
   bodies; it logs full detail and returns the problem shape with no internals
   (no stack traces, no driver messages).
4. **Validation fail-closed** — every input is a class-validator DTO behind the
   global `ValidationPipe`; an unvalidated body never reaches a provider.
5. **Dependency injection** — inject by constructor with `private readonly`;
   never `new` a provider — it bypasses the container and breaks test overrides.
6. **Strict TypeScript** — `tsc --noEmit` is the lint gate; `any` requires a
   written justification at the cast site.
7. **No floating config** — environment access happens once at bootstrap;
   providers receive typed config, never read `process.env`.

## Testing bar

Providers ≥ unit-tested per public method via the Nest testing module; controllers
≥ happy + error path via supertest; repositories integration-tested against a
disposable database.
