<!-- domain:DB | layer:reference | ssot:true | updated:2026-06-04 -->
# Redis Patterns — Caching, Rate Limiting, Locks, Queues

> P: The concrete recipes for the jobs Redis is actually used for, each with its consistency caveat.
> R: Adding caching, a rate limiter, a lock, or a queue on Redis.
> S: Choosing the durable store behind the cache — that's [db-design](../../db-design/SKILL.md).
> N: [SKILL.md](../SKILL.md), [operations.md](operations.md)

> Nav: [Skill](../SKILL.md)

## Cache-aside vs write-through

| | Cache-aside (default) | Write-through |
|---|---|---|
| read | check cache → miss → DB → populate | always from cache |
| write | write DB, **delete** cache key | write cache + DB together |
| consistency | self-healing (next read repopulates) | tighter, but cache write can fail mid-way |
| use when | most reads, tolerate brief staleness | read-heavy, must serve from cache |

Default to cache-aside with **delete-on-write** (not update-on-write): deleting
lets the next read pull fresh from the DB, so the cache can't hold a value the DB
never had. Updating the cache directly risks writing a value that races the DB.

## Stampede protection

When a hot key expires, every request misses at once and hammers the DB. Cures:
- **Jittered TTL** — `ex = base + random(0, spread)` so keys don't expire together.
- **Lock-on-miss** — first misser takes a short `SET NX` lock, recomputes, others
  briefly serve stale or wait.
- **Early recompute** — refresh at 90% of TTL in the background.

## Rate limiter (fixed window, atomic)

```lua
-- EVAL with KEYS[1]=bucket, ARGV[1]=limit, ARGV[2]=window_seconds
local n = redis.call('INCR', KEYS[1])
if n == 1 then redis.call('EXPIRE', KEYS[1], ARGV[2]) end
return n <= tonumber(ARGV[1]) and 1 or 0
```

`INCR` + `EXPIRE` in one Lua script is atomic — a separate `INCR` then `EXPIRE`
leaks a window if the client dies between them. Sliding-window needs a Sorted Set
of timestamps (`ZADD` + `ZREMRANGEBYSCORE`).

## Distributed lock (use with care)

```
SET lock:resource <token> NX EX 10        # acquire: only if absent, auto-expire
# release: Lua compare-and-delete so you only free YOUR lock
```

Always `NX` + a TTL (never a lock without expiry → deadlock on crash) and a unique
token released via a compare-and-delete Lua script. Every Redis lock — Redlock
included — is best-effort, never a correctness guarantee: a lease can expire while
its holder is GC-paused, leaving two holders. Keep the real invariant in the DB
([backend-fundamentals](../../backend-fundamentals/SKILL.md) § Concurrency), or use
a coordinator (etcd/Zookeeper) whose monotonic revision the resource checks as a
fencing token.

## Queue / worker

`LPUSH` to enqueue, `BRPOP` (blocking) in the worker. For at-least-once delivery
and consumer groups use **Streams** (`XADD` / `XREADGROUP` / `XACK`) — a plain
List drops the job if the worker crashes mid-process. Match the durability to the
cost of a lost job.
