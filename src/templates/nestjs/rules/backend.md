---
globs: ["src/backend/**/*.ts"]
alwaysApply: false
---

# NestJS Backend Rules (auto-loaded on src/backend/**/*.ts)

When editing any TypeScript file under `src/backend/` in a NestJS project, follow these standards:

- **Layering** — controller → provider → repository; imports flow one way only. Controllers stay transport-thin; business logic lives in providers, persistence in repositories.
- **Transport-free providers** — a provider never imports `@Req`/`@Res` or builds an HTTP response; it returns domain data and lets the controller serialize.
- **One error shaper** — only the global `AllExceptionsFilter` writes error bodies; it logs detail and returns the problem shape with no internals.
- **Validation fail-closed** — every input is a class-validator DTO behind the global `ValidationPipe`; an unvalidated body never reaches a provider.
- **Dependency injection** — inject by constructor with `private readonly`; never `new` a provider (it bypasses the container and breaks test overrides).
- **Strict TypeScript** — `tsc --noEmit` is the lint gate; `any` requires a written justification.
- **No floating config** — environment access happens once at bootstrap; providers receive typed config, never read `process.env`.

Canonical policy: `docs/engineering/nestjs-rules.md`
Playbook: `docs/playbooks/nestjs-service.md`
Primary skill: `nestjs`
