---
name: node-backend
tier: stack
domain: [backend]
description: Build production Node.js backends — Express/Fastify/Nest, the event loop, async/await correctness, streams, graceful shutdown, and not blocking the single thread. Use when writing a Node HTTP service, debugging "the server hangs / is slow under load", handling errors in async code, streaming large payloads, managing the process lifecycle, or choosing a framework. Triggers — "node server", "Express", "Fastify", "NestJS", "event loop", "the API is slow", "unhandled rejection", "stream", "graceful shutdown", any backend `*.js`/`*.ts` with `http`/`express`. Pairs with typescript (typed Node), api-design (the contract), security-web (server hardening), observability (logging/metrics), performance (profiling).
globs: ""
paths: []
last_reviewed: "2026-06-04"
versions_ref: versions.json
---

# Node.js Backend

Node runs your JavaScript on **one** thread with an event loop. It scales by never blocking that thread — every CPU-bound or sync call freezes *all* requests. The craft is async-correct code, streaming over buffering, and a clean process lifecycle.

> Audit a package.json for engine pin, lockfile, and risky scripts:
> `python3 scripts/check_package.py package.json`

## Never block the event loop

```javascript
// Wrong — sync read blocks EVERY in-flight request until the file loads
import { readFileSync } from "node:fs";
app.get("/data", (req, res) => res.send(readFileSync("big.json")));

// Correct — async yields the loop while I/O happens
import { readFile } from "node:fs/promises";
app.get("/data", async (req, res) => res.send(await readFile("big.json")));
```

`*Sync` calls, `JSON.parse` of a huge string, a tight `for` over a million items,
synchronous crypto/zlib — all freeze the loop and tank p99 for every concurrent
request. For genuine CPU work (image resize, hashing), offload to a Worker Thread
or a separate service; don't compute it inline. Detail → [references/event-loop.md](references/event-loop.md).

## Async errors must be caught — or the process dies

```javascript
// Wrong — a rejected promise in a handler with no catch → unhandledRejection
app.get("/x", async (req, res) => { const u = await db.get(); res.json(u); });
// (if db.get rejects, Express 4 doesn't catch async throws → hangs or crashes)

// Correct — wrap, or use a framework that awaits handlers (Express 5 / Fastify do)
app.get("/x", async (req, res, next) => {
  try { res.json(await db.get()); } catch (e) { next(e); }
});
```

In Express 4 an async handler that throws is **not** caught by the error
middleware — you need a wrapper (`express-async-errors`) or per-handler
try/catch. Express 5 and Fastify await handlers natively. Always register a
top-level `process.on("unhandledRejection")` + `uncaughtException` that logs and
exits — a silent rejection corrupts state.

## Stream large payloads, don't buffer

```javascript
// Wrong — loads the whole file into memory; 10 concurrent = OOM
res.send(await readFile("video.mp4"));

// Correct — pipe; constant memory regardless of size
import { createReadStream } from "node:fs";
createReadStream("video.mp4").pipe(res);
```

Buffering a large response holds it all in RAM per request; streams move it in
chunks at constant memory. Use `pipeline()` (handles backpressure + cleanup) over
manual `.pipe()` for production. Same for request bodies and DB cursors.

## Graceful shutdown (zero-downtime deploys)

```javascript
const server = app.listen(8080);
for (const sig of ["SIGTERM", "SIGINT"]) {
  process.on(sig, async () => {
    server.close();                 // stop accepting new connections
    await db.end();                 // drain pools / in-flight work
    process.exit(0);
  });
}
```

On deploy the orchestrator sends `SIGTERM`; without a handler, in-flight requests
are killed mid-response. Close the listener, drain connections, then exit. Set a
timeout so a stuck drain still exits.

## Framework pick

| | Express | Fastify | NestJS |
|---|---|---|---|
| style | minimal, middleware | minimal, fast, schema-first | opinionated, DI, decorators |
| async errors | v5 native (v4 needs wrapper) | native | native |
| validation | bring your own | built-in JSON-schema | class-validator |
| use when | simplest, huge ecosystem | perf + built-in validation | large team, structured DI |

Pin the Node version in `engines` and use the **Active LTS** in production, not
Current — Current ships breaking changes. Versions → [versions.json](versions.json).

## Anti-patterns (reject on sight)

- Any `*Sync` fs/crypto/zlib call on the request path → blocks the loop.
- An async route handler with no error path (Express 4) → unhandled rejection.
- No `process.on("unhandledRejection")` / `uncaughtException` → silent death.
- Buffering a large file/response instead of streaming → OOM under load.
- No `SIGTERM` handler → killed in-flight requests on every deploy.
- CPU-heavy work inline (sync hashing, big loops) → use a Worker Thread / queue.
- `npm install` in CI (mutates lockfile) → `npm ci` (lockfile-exact, reproducible).

## See also

- [references/event-loop.md](references/event-loop.md) — the loop phases, blocking sources, workers, backpressure.
- [references/async-and-errors.md](references/async-and-errors.md) — promises, error propagation, AbortController, timeouts.
- [assets/node-checklist.md](assets/node-checklist.md) — the ship gate.
- [typescript](../typescript/SKILL.md) · [api-design](../api-design/SKILL.md) · [security-web](../security-web/SKILL.md) · [observability](../observability/SKILL.md).
