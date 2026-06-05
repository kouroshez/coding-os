<!-- domain:DB | layer:asset | ssot:false | updated:2026-06-04 -->
# Redis Review Checklist

Run before shipping anything that touches Redis.

## Correctness
- [ ] Redis is a cache/ephemeral store, not the only home of must-keep data.
- [ ] Every cache key has a TTL (`ex=`/`EXPIRE`) — no immortal keys.
- [ ] Writes invalidate (delete) the cache key, not update it (cache-aside).
- [ ] Read-modify-write done atomically (`INCR`/Lua/`MULTI`), never across round trips.
- [ ] Data structure matches the access pattern (Hash for fields, Sorted Set for ranking, …).

## Operations
- [ ] `maxmemory` set + `maxmemory-policy allkeys-lru`/`lfu` for a cache (not `noeviction`).
- [ ] No `KEYS *` in app/prod paths — `SCAN` only.
- [ ] No unbounded big keys; sharded where they'd grow.
- [ ] Connection pool reused (not a new connection per request).
- [ ] Persistence mode matches the durability requirement (cache: none/RDB ok).

## Resilience
- [ ] Stampede protection on hot keys (jittered TTL / lock-on-miss).
- [ ] Rate limiter / lock uses atomic Lua + a TTL (no deadlock on crash).
- [ ] App degrades gracefully if Redis is down (fall back to DB, don't 500).

## Verify
- [ ] `redis-cli INFO | python3 scripts/analyze_info.py` → no flags (hit rate, evictions).
- [ ] `make skills-check-versions` — Redis version pin current.
