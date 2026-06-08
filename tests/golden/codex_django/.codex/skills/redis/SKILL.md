---
name: redis
tier: architecture
domain: [backend, data, infra]
description: Use Redis correctly as a cache, queue, rate limiter, and ephemeral store — pick the right data structure, caching pattern, eviction policy, and atomicity model. Use when adding caching, designing a key schema, choosing cache-aside vs write-through, setting TTLs/eviction, building a rate limiter or queue, debugging low hit-rate or evictions, or deciding Redis-vs-Postgres for a use case. Triggers — "cache", "Redis", "rate limit", "session store", "pub/sub", "cache invalidation", "TTL", "hit rate". Pairs with db-design (durable store — Redis is ephemeral), sql-authoring (the source of truth behind the cache), performance (cache as a latency lever).
globs: ""
paths: []
last_reviewed: "2026-06-04"
versions_ref: versions.json
---

# Redis

Redis is fast because it's in-memory and ephemeral — treat it as a cache/derived store, never the source of truth. The craft is choosing the data structure that makes the operation O(1), the caching pattern that stays consistent with the database, and the eviction policy that fails gracefully when memory fills.

> Summarize a verbose `redis-cli INFO` into health + flags:
> `redis-cli INFO | python3 scripts/analyze_info.py`

## Pick the structure that fits the access

| Need | Structure | Why |
|---|---|---|
| cache one value / counter | String (`GET/SET`, `INCR`) | atomic counter for free |
| object with fields | Hash (`HSET/HGET`) | update one field without re-serializing |
| queue / recent list | List (`LPUSH/RPOP`) | O(1) ends; `BRPOP` blocks for a worker |
| unique membership | Set (`SADD/SISMEMBER`) | dedupe, set algebra |
| leaderboard / time-ordered | Sorted Set (`ZADD/ZRANGE`) | score-ordered, O(log n) rank |
| event log / fan-out | Stream (`XADD/XREAD`) | durable, consumer groups |

Using a String + JSON where a Hash fits means re-reading and re-writing the whole blob to change one field. Match the structure to the operation.

## Cache-aside — the default pattern

```python
def get_user(uid):
    key = f"user:{uid}"                 # namespace:entity:id
    cached = r.get(key)
    if cached is not None:
        return json.loads(cached)       # hit
    user = db.fetch_user(uid)           # miss → source of truth
    r.set(key, json.dumps(user), ex=300)  # populate with a TTL — ALWAYS a TTL
    return user
```

```python
# Wrong — no TTL: stale forever, and the key never reclaims memory
r.set(key, value)

# Correct — every cache key has an expiry; staleness is bounded
r.set(key, value, ex=300)
```

On write, **invalidate** (`r.delete(key)`) rather than update the cache — let the
next read repopulate, so the cache can't drift from the DB. Patterns + write-through
trade-offs → [references/patterns.md](references/patterns.md).

## Atomicity — don't read-modify-write across round trips

```python
# Wrong — race: two clients read 5, both write 6; one increment lost
n = int(r.get("count")); r.set("count", n + 1)

# Correct — server-side atomic
r.incr("count")
```

For multi-key atomic logic use a Lua script (`EVAL`) or `MULTI/EXEC` — they run
without interleaving. A rate limiter is `INCR` + `EXPIRE` in one Lua script so the
window can't leak. `WATCH` gives optimistic locking when you must read-then-write.

## Eviction — decide what happens when memory fills

```
maxmemory 2gb
maxmemory-policy allkeys-lru      # cache: evict least-recently-used
# vs
maxmemory-policy noeviction       # source-of-truth data: reject writes (never silently drop)
```

A cache with `noeviction` (the default) stops accepting writes when full —
surprising outage. A cache should use `allkeys-lru`/`allkeys-lfu`. Data you can't
lose shouldn't be in Redis-as-only-store at all. Operations → [references/operations.md](references/operations.md).

## When NOT to use Redis

- As the **only** store for data you can't lose — it's memory-first; durability (AOF/RDB) is best-effort, not ACID.
- For relational queries / joins / ad-hoc filters → that's [Postgres](../db-design/SKILL.md).
- For values that don't expire and grow unbounded → you'll OOM. Everything ephemeral gets a TTL.
- As a message bus needing delivery guarantees → Streams help, but Kafka/SQS may fit better.

## Anti-patterns (reject on sight)

- `KEYS *` in production → O(n) blocking scan; use `SCAN` (cursor, non-blocking).
- A cache key with no TTL → memory leak + unbounded staleness.
- Read-modify-write across round trips → race; use `INCR`/Lua/`MULTI`.
- `maxmemory-policy noeviction` on a pure cache → write outage when full.
- One giant Hash/Set holding millions of fields ("big key") → blocks on access/expire; shard it.
- Caching the DB write path (write-through) without invalidation discipline → drift.

## See also

- [references/patterns.md](references/patterns.md) — cache-aside vs write-through, invalidation, rate limiter, locks, queues.
- [references/operations.md](references/operations.md) — persistence (RDB/AOF), eviction, big-key detection, INFO metrics.
- [assets/redis-checklist.md](assets/redis-checklist.md) — the ship gate.
- [db-design](../db-design/SKILL.md) · [performance](../performance/SKILL.md) · [sql-authoring](../sql-authoring/SKILL.md).
