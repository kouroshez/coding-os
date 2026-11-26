# PostgreSQL — Patterns Worth Knowing

The Postgres-specific features that punch above their weight. Each is a real tool you'll reach for in this project's stack (Go business backend + Python AI adapter + RN client → Postgres).

## Advisory Locks — App-level Mutex via Postgres

When you need cross-process serialization without Redis or ZooKeeper.

```sql
-- Try to acquire (non-blocking). Returns boolean.
SELECT pg_try_advisory_lock(42);     -- key = bigint, app-defined namespace

-- Blocking acquire.
SELECT pg_advisory_lock(42);

-- Release.
SELECT pg_advisory_unlock(42);

-- Or transaction-scoped (released on COMMIT/ROLLBACK; can't forget):
SELECT pg_advisory_xact_lock(42);
```

Real uses:

- **Single-leader cron**: each replica calls `pg_try_advisory_lock(JOB_ID)`; only one wins and runs the job.
- **Per-user mutex**: `pg_advisory_lock(hashtext('user:' || user_id))` for "only one in-flight payment per user".
- **Migration coordination**: ensure only one app instance runs the data backfill.

Caveats:

- Bigint key is a 32+32 partition (or one 64-bit). Pick a namespace prefix.
- App holds the lock; if app dies, Postgres releases on disconnect. Keep advisory_xact for safety.
- Doesn't work across logical replication. Single-DB only.

## LISTEN / NOTIFY — Lightweight Pub/Sub

Free real-time fanout to all listeners on the same DB.

```sql
-- Notifier (in any transaction):
NOTIFY orders_updated, '{"order_id": "ord_123", "status": "paid"}';

-- Listener (long-lived connection):
LISTEN orders_updated;
-- Then poll the connection for notifications.
```

Use for:

- **Cache invalidation** across app replicas.
- **WebSocket fanout**: backend NOTIFY → app process forwards to connected clients.
- **Job queue tickle**: workers `LISTEN` instead of polling — wake on new work.

Caveats:

- Payload limit ~8KB. Pass an ID, not the whole record.
- Notifications are NOT persisted. Listener offline = missed event. Pair with a polling fallback for at-least-once.
- Per-channel ordering, not global.

## Postgres as a Job Queue

For ≤100 jobs/sec, Postgres beats Redis (one less moving part):

```sql
CREATE TABLE jobs (
    id           BIGSERIAL   PRIMARY KEY,
    queue        TEXT        NOT NULL,
    payload      JSONB       NOT NULL,
    run_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    state        TEXT        NOT NULL DEFAULT 'queued',
    attempts     INT         NOT NULL DEFAULT 0,
    locked_at    TIMESTAMPTZ,
    locked_by    TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_jobs_queue_runat
    ON jobs(queue, run_at)
    WHERE state = 'queued';

-- Worker dequeue (atomic with FOR UPDATE SKIP LOCKED):
WITH next AS (
    SELECT id FROM jobs
    WHERE queue = $1
      AND state = 'queued'
      AND run_at <= NOW()
    ORDER BY run_at
    LIMIT 1
    FOR UPDATE SKIP LOCKED
)
UPDATE jobs
SET state = 'running',
    locked_at = NOW(),
    locked_by = $2,
    attempts = attempts + 1
FROM next
WHERE jobs.id = next.id
RETURNING jobs.id, jobs.payload;
```

`FOR UPDATE SKIP LOCKED` is the magic — multiple workers can dequeue concurrently without contention. Pair with `LISTEN jobs` for instant pickup.

When to outgrow this: >100 jobs/sec sustained, or you need fanout / priorities / delays beyond what a few SQL clauses express. Move to Redis Streams / Sidekiq / Asynq / rivers.

## Row-Level Security (RLS) — Multi-tenant Safety Net

Postgres can enforce "user can only see their own rows" at the storage layer. App bug → no data leak.

```sql
ALTER TABLE orders ENABLE ROW LEVEL SECURITY;

CREATE POLICY orders_owner ON orders
    FOR ALL
    TO app_role
    USING (user_id = current_setting('app.user_id'))
    WITH CHECK (user_id = current_setting('app.user_id'));

-- App sets the session var per-request:
SET app.user_id = 'usr_abc123';
SELECT * FROM orders;  -- automatically filtered.
```

For this project:

- Use RLS for the FastAPI AI service if it serves multi-tenant inference.
- Skip for the Go backend if it's already strict about tenant_id in every query (slight overhead saved).
- Combine with PgBouncer transaction-mode + per-request `SET LOCAL app.user_id` to avoid leakage between pooled queries.

## Full-Text Search — `tsvector` + GIN

For "search this column for words" without spinning up Elasticsearch:

```sql
ALTER TABLE lessons
    ADD COLUMN search_doc tsvector
    GENERATED ALWAYS AS (
        setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
        setweight(to_tsvector('english', coalesce(body, '')), 'B')
    ) STORED;

CREATE INDEX idx_lessons_search ON lessons USING GIN (search_doc);

-- Query:
SELECT id, title, ts_rank(search_doc, query) AS rank
FROM lessons,
     to_tsquery('english', 'react & native & navigation') AS query
WHERE search_doc @@ query
ORDER BY rank DESC
LIMIT 20;
```

Good enough for: docs search, lesson search, message search up to ~10M rows.

Use Meilisearch / Typesense / OpenSearch when: typo tolerance + faceting + 100M+ docs + multi-language.

## pgvector — Embedding Storage for the AI Adapter

For the FastAPI AI service: store + query high-dimensional embeddings in Postgres. No need for a separate Pinecone/Qdrant for moderate scale (<10M vectors).

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE message_embeddings (
    message_id  TEXT PRIMARY KEY REFERENCES messages(id) ON DELETE CASCADE,
    embedding   vector(1536),     -- OpenAI ada-002 dim; adjust per model
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- HNSW index (best speed/quality default; PG ≥ 16 with pgvector 0.5+):
CREATE INDEX idx_message_embeddings_hnsw
    ON message_embeddings USING hnsw (embedding vector_cosine_ops);

-- Nearest-neighbor query:
SELECT message_id, 1 - (embedding <=> $1::vector) AS similarity
FROM message_embeddings
ORDER BY embedding <=> $1::vector       -- cosine distance
LIMIT 10;
```

Operators:

- `<->` — Euclidean distance.
- `<=>` — Cosine distance (most common for text embeddings).
- `<#>` — Inner product (negate for similarity).

Tune `hnsw.ef_search` and `vector_cosine_ops` parameters to your recall/latency target. See <https://github.com/pgvector/pgvector>.

## Partitioning — Time-Series + Audit Tables

When a table has 100M+ rows but most queries hit the recent slice, partition by time:

```sql
CREATE TABLE events (
    id          BIGINT      NOT NULL,
    user_id     TEXT        NOT NULL,
    event_type  TEXT        NOT NULL,
    payload     JSONB,
    created_at  TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (id, created_at)
) PARTITION BY RANGE (created_at);

CREATE TABLE events_2026_04 PARTITION OF events
    FOR VALUES FROM ('2026-04-01') TO ('2026-05-01');

CREATE TABLE events_2026_05 PARTITION OF events
    FOR VALUES FROM ('2026-05-01') TO ('2026-06-01');

-- Use pg_partman to auto-create monthly partitions.
```

Wins:

- Index per partition is small + fast.
- `DROP TABLE events_2025_01` is instant (vs `DELETE FROM events WHERE ... < '2025-02-01'` which churns).
- Query planner prunes partitions outside the date range.

Pitfalls:

- Cannot have a UNIQUE constraint that doesn't include the partition key.
- Foreign keys TO a partitioned table work; FROM a partitioned table to another is supported only since PG 12+.
- Auto-vacuum tuning per partition.

## Generated Columns — Indexable Derived Values

Compute once, store, index:

```sql
CREATE TABLE users (
    id              TEXT PRIMARY KEY,
    email           TEXT NOT NULL,
    email_lower     TEXT GENERATED ALWAYS AS (LOWER(email)) STORED,
    full_name       TEXT NOT NULL,
    full_name_tsv   TSVECTOR GENERATED ALWAYS AS (
        to_tsvector('english', full_name)
    ) STORED
);

CREATE UNIQUE INDEX idx_users_email_lower ON users(email_lower);
CREATE INDEX idx_users_full_name_tsv ON users USING GIN(full_name_tsv);
```

Two flavors:

- `STORED` — materialized; takes disk; can be indexed.
- `VIRTUAL` (PG 18+) — computed on read; can NOT be indexed.

## Transactions Done Right

### Isolation Levels — Default is Wrong for Money

Postgres default is `READ COMMITTED`. For financial / inventory operations:

```sql
BEGIN ISOLATION LEVEL SERIALIZABLE;
-- ... your work ...
COMMIT;
```

`SERIALIZABLE` gives you "as if the transactions ran one after another". Costs: occasional `serialization_failure` (40001) errors on conflict — your app must retry. Worth it for any operation where stale reads cause wrong outcomes.

For "single row update" patterns, `SELECT ... FOR UPDATE` (row lock) on `READ COMMITTED` is enough.

### Optimistic Locking

For UI-driven edits where conflict is rare but possible:

```sql
ALTER TABLE orders ADD COLUMN version INT NOT NULL DEFAULT 1;

-- App reads (id, version, ...).
-- App writes:
UPDATE orders
SET status = 'shipped', version = version + 1
WHERE id = $1 AND version = $2;
-- Check rowcount; if 0, return 412 Precondition Failed.
```

Pair with `If-Match` / `ETag` HTTP headers (see api-design skill).

### Avoid `idle in transaction`

App opens a transaction, does network I/O, returns to commit. Holds a lock for seconds.

```sql
SET idle_in_transaction_session_timeout = '5s';
```

Refuses transactions that hold locks idly. Forces app to either commit fast or finish work first.

## EXPLAIN — Read the Plan

```sql
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT, VERBOSE)
SELECT ...;
```

Look for:

- **`Seq Scan`** on a large table = missing index.
- **`Rows Removed by Filter:`** high = wrong index (predicate not selective).
- **`Bitmap Heap Scan`** + many heap fetches = index is selective but query needs columns not in the index → `INCLUDE`.
- **`Sort Method: external merge Disk:`** = work_mem too low or missing index that satisfies ORDER BY.
- **`Nested Loop`** with high outer rowcount = consider hash join (set `enable_nestloop = off` to test).
- **Big difference between estimated and actual rowcount** = stats stale, run `ANALYZE table_name`.

`auto_explain` extension auto-logs slow queries with their plans. Enable in production at a 500ms threshold.

## Connection / Pool Math

```
max_connections (Postgres) = N
PgBouncer pool_size (transaction mode) = N
Per-app-replica pool_max = M

Total app-side conns = M × replicas
Total Postgres conns = pool_size of PgBouncer (≪ M × replicas)
```

For a 1-replica AI service:

- Postgres `max_connections = 100` (modest server).
- PgBouncer `pool_size = 80` (leave headroom for migrations + monitoring).
- App `pool_max = 20` per replica × 4 replicas = 80 app conns total.
- App goes through PgBouncer → only ever uses 80 actual Postgres slots.

## Backup + PITR

Conventions:

- Daily logical backup (`pg_dump`) for point-in-time test restore.
- Continuous WAL archiving (e.g., `pgbackrest`) for true PITR — restore to any second of the past 30 days.
- Quarterly **restore test**: pick a recent backup, restore to a fresh DB, run smoke tests. Backups you don't test are not backups.

## References

- PostgreSQL docs (16/17/18) — primary source.
- *use-the-index-luke.com* (Markus Winand) — the index reference.
- *PgBouncer documentation* — pooling modes + tuning.
- pgvector: <https://github.com/pgvector/pgvector>
- pg_partman: <https://github.com/pgpartman/pg_partman>
- Brandur Leach — series on Postgres job queues, advisory locks, listen/notify.
