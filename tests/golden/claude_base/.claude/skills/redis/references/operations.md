<!-- domain:DB | layer:reference | ssot:true | updated:2026-06-04 -->
# Redis Operations — Persistence, Eviction, Big Keys, Metrics

> P: Run Redis safely — what persistence guarantees you have, how memory is reclaimed, and which metrics matter.
> R: Configuring a Redis instance or debugging memory/latency.
> S: Application-side patterns — see [patterns.md](patterns.md).
> N: [SKILL.md](../SKILL.md), [operations.md](operations.md)

> Nav: [Skill](../SKILL.md)

## Persistence — know your guarantee

| Mode | Guarantee | Cost |
|---|---|---|
| none (default cache) | data lost on restart | fastest |
| RDB snapshot | point-in-time, lose since last snapshot | periodic fork |
| AOF (append-only) | every write (or every second) | larger file, replay on start |
| RDB + AOF | best durability | both costs |

Even AOF `appendfsync everysec` can lose ~1s of writes — Redis is **not** ACID.
If losing data is unacceptable, the source of truth is Postgres; Redis caches it.

## Eviction policies

| Policy | Behaviour | Use for |
|---|---|---|
| `noeviction` (default) | reject writes when full | data you must not drop (but then why Redis-only?) |
| `allkeys-lru` | evict least-recently-used | general cache |
| `allkeys-lfu` | evict least-frequently-used | cache with hot/cold skew |
| `volatile-lru` | LRU among keys with a TTL only | mixed cache + persistent keys |

Set `maxmemory` explicitly — without it Redis grows until the OS OOM-kills it. A
cache wants `allkeys-lru` + a `maxmemory` ceiling.

## Big keys — the silent latency source

A single key holding millions of elements blocks the event loop on access,
expire, and migration (Redis is single-threaded for commands). Find them:

```bash
redis-cli --bigkeys                  # sampled scan, safe in production
redis-cli --memkeys                  # by memory
```

Shard a big Hash/Set across many keys (`user:{id}:sessions` per user, not one
global `sessions` set). Never `KEYS *` to find them — `SCAN` (cursor) or the
sampled `--bigkeys`.

## Metrics that matter (from INFO)

| Metric | Healthy | Bad signal |
|---|---|---|
| `keyspace_hits` / `(hits+misses)` | > 0.8 | low → cache too small / wrong keys |
| `evicted_keys` | ~0 for a sized cache | rising → undersized or wrong policy |
| `used_memory` vs `maxmemory` | headroom | at ceiling → evictions or write rejects |
| `connected_clients` | stable | climbing → connection leak (pool not reused) |
| `instantaneous_ops_per_sec` | baseline | spikes → stampede / hot key |

`scripts/analyze_info.py` parses `redis-cli INFO` and surfaces exactly these +
flags (low hit rate, evictions under `noeviction`) — one summary, not the full dump.

## Connection pooling

Open a pool once and reuse it; a new TCP connection per request exhausts
`connected_clients` and adds handshake latency. Every client library has a pool —
configure max size to match your worker concurrency, not higher.
