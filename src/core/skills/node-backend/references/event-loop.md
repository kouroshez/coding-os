<!-- domain:BACKEND | layer:reference | ssot:true | updated:2026-06-04 -->
# The Node Event Loop — Phases, Blocking, Workers

> P: How the single thread schedules work, what blocks it, and how to do CPU work without freezing requests.
> R: Debugging latency under load, or adding any CPU-heavy operation.
> S: Async error handling — see [async-and-errors.md](async-and-errors.md).
> N: [SKILL.md](../SKILL.md), [node-checklist.md](../assets/node-checklist.md)

> Nav: [Skill](../SKILL.md)

## One thread, phases per tick

The loop cycles through phases: **timers** (`setTimeout`), **pending callbacks**,
**poll** (I/O — most of your handlers run here), **check** (`setImmediate`),
**close**. Between every callback it drains the **microtask queue** (resolved
promises, `queueMicrotask`, `process.nextTick`). Your code shares this one thread
with every other request — so a callback that runs 200 ms of sync work adds 200 ms
of latency to everything else waiting.

## What blocks (and the fix)

| Blocker | Fix |
|---|---|
| `fs.readFileSync`, `crypto.*Sync`, `zlib.*Sync` | the async variant (`fs/promises`, callback crypto) |
| `JSON.parse`/`stringify` of MBs | stream-parse, or do it in a Worker |
| tight loop over 10⁶+ items | chunk with `setImmediate`, or a Worker Thread |
| sync hashing / bcrypt rounds inline | async bcrypt / a Worker / a queue |
| a regex with catastrophic backtracking | fix the regex (ReDoS is a DoS *and* a block) |

A microtask that recurses (`process.nextTick` calling itself) **starves** the I/O
phase — the loop never reaches poll. Prefer `setImmediate` for "run after current
I/O" so you don't starve.

## CPU work — off the main thread

```javascript
import { Worker } from "node:worker_threads";
// hash/resize/parse in a worker; main thread stays responsive
const result = await new Promise((resolve, reject) => {
  const w = new Worker("./hash-worker.js", { workerData: payload });
  w.on("message", resolve); w.on("error", reject);
});
```

Worker Threads have their own loop + memory; use them for CPU-bound tasks. For
heavy or bursty work, a separate queue/worker service (BullMQ + Redis) is better
than inline workers — it survives restarts and scales independently.

## Backpressure — respect the consumer's pace

```javascript
import { pipeline } from "node:stream/promises";
await pipeline(source, transform, destination);   // honors backpressure + cleans up on error
```

A fast producer (`source.on("data")` → `dest.write()`) that ignores `write()`
returning `false` buffers unbounded in memory → OOM. `pipeline()` (or `.pipe()`)
pauses the source when the destination is full. Never hand-roll the data/drain
dance in production.

## Measure

`--prof` / `clinic.js` / `0x` flame graphs show where the loop spends time;
`event-loop-lag` (or `perf_hooks.monitorEventLoopDelay`) exposes lag as a metric —
alert on it. Rising loop lag under load = something is blocking the thread.
