<!-- domain:BACKEND | layer:rules | ssot:true | updated:{{DATE}} -->
# Express Engineering Rules

Purpose: Non-negotiable conventions for the {{PROJECT_NAME}} Express backend.
Read when: Editing anything under `src/backend/`.
Skip when: Frontend/mobile work.
Read next: [Express Service Playbook](../playbooks/express-service.md)

> Nav: [Master Index](../00-index.md)

## Hard rules

1. **Layering** — routes → services → repositories, imports flow one way only
   (the table in the `node-express` skill is the SSOT).
2. **Async safety** — every async handler is wrapped; an unhandled rejection
   in a route is a build-blocking review finding.
3. **One error shaper** — only `middleware/error-handler.ts` writes error
   bodies; it logs full detail and returns the problem shape with no
   internals (no stack traces, no driver messages).
4. **Validation fail-closed** — unvalidated `req.body` never crosses into a
   service; reject with 400 + problem shape on schema mismatch.
5. **Strict TypeScript** — `tsc --noEmit` is the lint gate; `any` requires a
   written justification at the cast site.
6. **No floating config** — environment access happens once at bootstrap;
   services receive typed config, never read `process.env`.

## Testing bar

Services ≥ unit-tested per public method; routes ≥ happy + error path via
supertest; repositories integration-tested against a disposable database.
