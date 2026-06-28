---
globs: ["src/backend/**/*.ts"]
alwaysApply: false
---

# Express Backend Rules (auto-loaded on src/backend/**/*.ts)

When editing any TypeScript file under `src/backend/` in an Express project, follow these standards:

- **Layering** — routes → services → repositories; imports flow one way only (the table in the `node-express` skill is the SSOT).
- **Async safety** — every async handler is wrapped; an unhandled rejection in a route is a build-blocking review finding.
- **One error shaper** — only `middleware/error-handler.ts` writes error bodies; it logs full detail and returns the problem shape with no internals (no stack traces, no driver messages).
- **Validation fail-closed** — unvalidated `req.body` never crosses into a service; reject with 400 + problem shape on schema mismatch.
- **Strict TypeScript** — `tsc --noEmit` is the lint gate; `any` requires a written justification at the cast site.
- **No floating config** — environment access happens once at bootstrap; services receive typed config, never read `process.env`.
- **Testing bar** — services unit-tested per public method; routes covered happy + error path via supertest; repositories integration-tested against a disposable database.

Canonical policy: `docs/engineering/express-rules.md`
Playbook: `docs/playbooks/express-service.md`
Primary skill: `node-express`
