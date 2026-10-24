<!-- domain:BACKEND | layer:reference | ssot:true | updated:2026-06-04 -->
# Async & Error Handling in Node

> P: Propagate, time out, and cancel async work so one failure doesn't crash the process or hang a request.
> R: Writing any async handler, calling external services, or wiring shutdown.
> S: Loop scheduling / blocking — see [event-loop.md](event-loop.md).
> N: [SKILL.md](../SKILL.md), [node-checklist.md](../assets/node-checklist.md)

> Nav: [Skill](../SKILL.md)

## The two process-level nets (always install)

```javascript
process.on("unhandledRejection", (reason) => { logger.error({ reason }, "unhandledRejection"); process.exit(1); });
process.on("uncaughtException", (err) => { logger.error({ err }, "uncaughtException"); process.exit(1); });
```

An unhandled rejection or thrown error with no catch will, by default, terminate
the process (modern Node) — but silently if you don't log it. Log, then exit
non-zero so the orchestrator restarts a clean process. Do **not** try to "recover"
after an `uncaughtException` — the state is unknown; exit.

## Propagate, don't swallow

```javascript
// Wrong — swallows the error; caller thinks it succeeded
try { await save(x); } catch { /* ignore */ }

// Correct — handle or rethrow; never an empty catch
try { await save(x); }
catch (err) { logger.warn({ err }, "save failed"); throw err; }
```

An empty `catch` is a lie to the caller. Either handle it meaningfully (retry,
fallback, user-facing error) or rethrow. In Express, `next(err)` routes to the
error middleware; never `res.send` a raw error (leaks internals).

## Timeouts + cancellation with AbortController

```javascript
const ac = new AbortController();
const t = setTimeout(() => ac.abort(), 5000);
try {
  const r = await fetch(url, { signal: ac.signal });   // aborts at 5s
} finally { clearTimeout(t); }
```

Every outbound call (HTTP, DB) needs a timeout — without one a hung upstream
holds your request (and its loop slot) forever. `AbortController` cancels fetch,
streams, and many libraries; propagate the request's signal so a client
disconnect cancels downstream work.

## Concurrency control

```javascript
// Wrong — fires 10000 DB calls at once; exhausts the pool, OOMs
await Promise.all(ids.map((id) => db.get(id)));

// Correct — bounded concurrency
import pLimit from "p-limit";
const limit = pLimit(20);
await Promise.all(ids.map((id) => limit(() => db.get(id))));
```

`Promise.all` over a huge array launches everything simultaneously. Bound it
(`p-limit`, a queue, or batched `for` loops) to your pool/rate limits. Use
`Promise.allSettled` when one failure shouldn't reject the whole batch.
