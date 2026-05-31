---
name: db-design
description: Design and evolve PostgreSQL schemas that survive scale and refactors. Use when modeling a new domain, choosing between normalization and denormalization, designing indexes for known query patterns, writing migrations safely, picking ORM-vs-raw-SQL trade-offs, deciding on soft delete vs hard delete, or evaluating NoSQL document/KV/wide-column for a use case. Targets PostgreSQL 16+ as the default; calls out MongoDB / Redis / DynamoDB where they're the better fit.
tier: cross-cutting
domain: [data, backend]
last_reviewed: "2026-05-11"

---

# Database Design — PostgreSQL First

A practical design playbook for the project's stack: PostgreSQL as the system of record, accessed by the Go+Fiber business core and the Python+FastAPI AI adapter, with hexagonal repositories isolating the rest of the codebase from schema specifics.

## When to Use This Skill

- Modeling the schema for a new bounded context (orders, users, lessons, payments).
- Adding a column or table that will see growth.
- Choosing PK / FK shapes (UUID? bigint? prefixed string?).
- Designing indexes after seeing query patterns or EXPLAIN output.
- Writing migrations that touch live data (never just on a fresh DB).
- Picking ORM (sqlc / GORM / SQLAlchemy / Drizzle) vs raw SQL for a feature.
- Deciding on soft delete vs hard delete + audit table.
- Evaluating Redis (cache/queue) vs Postgres (LISTEN/NOTIFY, advisory locks) for a side-channel.

Skip when: prototyping with a sqlite that will be thrown away. Use this skill before the throw-away gets promoted.

## The Three Rules

1. **Constraints in the database, not the application.** `NOT NULL`, `CHECK`, `UNIQUE`, `FOREIGN KEY` enforced by Postgres survive bugs in the app, replays of stale code, and direct DBA fixes. Application-only invariants are constantly violated by accident.
2. **Migrations are forward-only and additive.** Never drop a column the same release you stop writing to it. Two-phase: stop writing → wait → drop. See [references/migration-discipline.md](references/migration-discipline.md).
3. **Your queries determine your indexes, not the other way around.** Don't index speculatively; index after you see EXPLAIN output for the queries that matter.

## Modeling Choices

### Primary Keys

| Style | Pros | Cons | Use when |
|---|---|---|---|
| **bigint identity** | Compact, sequential, fast B-tree, predictable | Leaks count, predictable, one-DB-only | Internal high-volume tables (audit log, events). |
| **UUID v7** (time-ordered) | Globally unique, mergeable, sortable | 16 bytes, slightly bigger indexes | Default for user-visible entities. Postgres 18 has built-in `uuidv7()`; on 16/17 use `pg_uuidv7` extension or app-side. |
| **UUID v4** (random) | Globally unique, no info leakage | Index bloat from random insertion order, 4× page splits vs v7 | Avoid for primary keys at scale. Fine for IDs that never get indexed. |
| **Prefixed text** (`ord_8h2k4n9d3p7q`) | Self-documenting in logs, debug-friendly | App-side ID generation, slightly larger | Public API surface (Stripe pattern). Pair with a UUID v7 internally if needed. |

**Default for this project**: prefixed text IDs (`usr_`, `ord_`, `lsn_`, `pay_`) generated app-side from UUID v7 + base32. Internally, the column is `TEXT NOT NULL PRIMARY KEY`. Postgres handles text PKs well at this size.

### Foreign Keys

ALWAYS declare them. ALWAYS index them.

```sql
-- Postgres does NOT auto-index foreign key columns. Forgetting this
-- is the #1 cause of slow DELETE / UPDATE on the parent table.
CREATE TABLE order_items (
    id          TEXT       PRIMARY KEY,
    order_id    TEXT       NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    sku         TEXT       NOT NULL,
    quantity    INT        NOT NULL CHECK (quantity > 0),
    UNIQUE (order_id, sku)
);

CREATE INDEX idx_order_items_order_id ON order_items(order_id);
```

Cascade rules — pick deliberately:

- `ON DELETE CASCADE` — the child has no meaning without the parent (line items without an order).
- `ON DELETE RESTRICT` — refuse the delete if children exist (default; force the app to clean up).
- `ON DELETE SET NULL` — the FK is optional; preserve the child (e.g., assigned-by user gets nulled on user delete).

### Nullability

Default: `NOT NULL` on every column. Add nullability only with a written reason. `NULL` means "we don't know" — distinct from "we know it's absent" (use a sentinel or separate flag).

Common mistakes: `email VARCHAR(255)` nullable when "user without email" is impossible → fix data + make it `NOT NULL`.

### Time Columns

```sql
created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
deleted_at  TIMESTAMPTZ,                      -- soft delete (see below)
```

- ALWAYS `TIMESTAMPTZ`, never `TIMESTAMP` (without TZ). The latter loses information at the boundary and bites you in 3 years.
- Update `updated_at` via trigger so app bugs can't forget:
  ```sql
  CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger AS $$
  BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
  $$ LANGUAGE plpgsql;

  CREATE TRIGGER orders_set_updated_at BEFORE UPDATE ON orders
      FOR EACH ROW EXECUTE FUNCTION set_updated_at();
  ```

### Soft Delete vs Hard Delete

Soft delete (`deleted_at TIMESTAMPTZ`) when:

- Compliance / audit requires keeping records.
- Users can "undo" deletes within a window.
- Foreign-key cleanup is impractical.

Hard delete when:

- GDPR right-to-be-forgotten kicks in.
- Storage cost > legal/business value.
- The data was always ephemeral (sessions, OTPs).

**Soft delete pitfalls**:

- Every query needs `WHERE deleted_at IS NULL` — easy to forget. Mitigate with a view: `CREATE VIEW active_orders AS SELECT * FROM orders WHERE deleted_at IS NULL;` and treat the view as the default.
- Unique constraints break: `UNIQUE(email)` on a soft-deleted row blocks re-registration. Use `UNIQUE(email) WHERE deleted_at IS NULL` (partial unique index).

```sql
CREATE UNIQUE INDEX users_email_active_unique
    ON users(email) WHERE deleted_at IS NULL;
```

### Money

```sql
amount       BIGINT      NOT NULL,           -- minor units (cents)
currency     CHAR(3)     NOT NULL,           -- ISO 4217: USD, EUR, IRR
CHECK (amount >= 0 OR allow_negative)
```

NEVER use `FLOAT` / `REAL` / `DOUBLE PRECISION` for money. NEVER use `NUMERIC` without a written reason (slow + complex; integer cents covers 99% of cases).

For exotic currencies (JPY has no minor unit; KWD has 3 digits), store the actual minor-unit count and document per-currency multiplication factor in app code.

### Enums vs Lookup Tables vs CHECK

Three options for "status" columns:

```sql
-- (a) Postgres native ENUM — compact, fast, hard to evolve
CREATE TYPE order_status AS ENUM ('pending', 'paid', 'shipped', 'cancelled');

-- (b) CHECK constraint with TEXT — flexible, slightly bigger
status TEXT NOT NULL CHECK (status IN ('pending', 'paid', 'shipped', 'cancelled'))

-- (c) Lookup table with FK — most flexible, joins required
status_id INT NOT NULL REFERENCES order_statuses(id)
```

**Rule of thumb**:

- **(b) CHECK + TEXT** is the right default. Easy to add values (just update the constraint), readable in queries, doesn't need joins.
- **(a) ENUM** when set is truly fixed and shows up in millions of rows.
- **(c) Lookup table** when the set has metadata (label, color, ordering) the app needs to render.

Avoid mixing: pick one per concept project-wide.

### JSON Columns

Postgres `JSONB` is genuinely useful for:

- **Settings / preferences** with no fixed schema and no querying needs.
- **Webhook payloads** archived for replay / debugging.
- **Polymorphic event bodies** in an event-store table.

NOT for:

- Anything you'll filter on frequently. Use a real column.
- Anything with a stable schema. That's just a table — make it one.
- Money. Always real columns.

If you must filter on JSONB, add a GIN index:

```sql
CREATE INDEX idx_orders_meta_gin ON orders USING GIN (metadata jsonb_path_ops);
-- Use jsonb_path_ops for ?, ?| , ?& operators (smaller index than the default).
```

### Polymorphic Associations — Don't

```sql
-- ANTI-PATTERN: comments table polymorphic on (target_type, target_id)
CREATE TABLE comments (
    target_type TEXT,  -- 'post' | 'video' | 'order'
    target_id   TEXT,
    body        TEXT,
    -- impossible to FK; impossible to JOIN cleanly
);
```

Replace with separate tables: `post_comments`, `video_comments`, `order_comments`. Yes, more tables. Yes, real FKs work. Yes, this pays off.

If the polymorphism is genuine (any user-content can be commented on), use `comments` + a `comment_targets` join table per target type, all with proper FKs.

## Indexing Strategy

### Read the Query First

Don't index speculatively. Find the slow query, run `EXPLAIN (ANALYZE, BUFFERS)`, see the plan, then add the index.

```sql
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT id, total FROM orders
WHERE user_id = $1 AND status = 'paid'
ORDER BY created_at DESC LIMIT 20;

-- Look for:
--   "Seq Scan on orders" → missing index
--   "Rows Removed by Filter: <high>" → wrong index
--   "Sort Method: external merge" → spilling to disk; add index that satisfies ORDER BY
```

### Index Types

| Type | Use for |
|---|---|
| **B-tree** (default) | Equality + range + ORDER BY. Most common. |
| **Hash** | Equality only; rarely worth it (B-tree is fine). |
| **GIN** | Full-text, JSONB, arrays — "contains" semantics. |
| **GiST** | Geometric, ranges, full-text (older). |
| **BRIN** | Huge append-only tables sorted by insertion (audit logs, time-series). 1000× smaller than B-tree. |

### Composite Indexes — Order Matters

Match the WHERE + ORDER BY of your query. The leftmost columns are usable for partial matches; rightward columns are not.

```sql
-- Query: WHERE user_id = $1 AND status = 'paid' ORDER BY created_at DESC
CREATE INDEX idx_orders_user_status_created
    ON orders(user_id, status, created_at DESC);
-- Order: equality cols first, then range/ORDER BY col last.
```

### Partial Indexes

Index only rows that matter. Massive size reduction for "active" / "pending" subsets.

```sql
-- Common: only paid orders — most queries filter on this.
CREATE INDEX idx_orders_paid_user
    ON orders(user_id, created_at DESC)
    WHERE status = 'paid';

-- Common: only undeleted rows.
CREATE INDEX idx_users_email_active
    ON users(email) WHERE deleted_at IS NULL;
```

### Covering Indexes (INCLUDE)

When your query selects 2 small columns and filters on a 3rd, INCLUDE lets the index satisfy the query without a heap fetch.

```sql
CREATE INDEX idx_orders_user_paid_covering
    ON orders(user_id) INCLUDE (id, total)
    WHERE status = 'paid';
```

### What Not to Index

- Columns with low cardinality (`is_active` boolean) — usually a partial index on the rare value works.
- Columns rarely filtered on.
- Tables that are 99% writes, 1% reads (background queues, audit append).
- Anything you can't see used in `pg_stat_user_indexes` after a week — drop it.

### Maintenance

```sql
-- Weekly:
SELECT schemaname, relname, indexrelname, idx_scan, idx_tup_read, idx_tup_fetch
FROM pg_stat_user_indexes
ORDER BY idx_scan ASC;
-- Drop indexes with idx_scan = 0 after a full week of normal traffic.

-- VACUUM + ANALYZE on a regular schedule (autovacuum usually fine; tune
-- per-table for very-large or hot tables).
```

For the full migration playbook (online additive changes, expand-contract, backfills, NOT NULL adds, FK adds), see [references/migration-discipline.md](references/migration-discipline.md).

For Postgres-specific patterns (advisory locks, LISTEN/NOTIFY, full-text search, pgvector for embeddings, partitioning), see [references/postgres-patterns.md](references/postgres-patterns.md).

## ORM vs Raw SQL Trade-Off

Pick per-query, not per-codebase:

| Use ORM (sqlc / SQLAlchemy / Drizzle / GORM) when | Use raw SQL when |
|---|---|
| CRUD on a single row by PK | Multi-table joins with non-trivial filters |
| Simple list with 1–2 filters | Aggregations, window functions, CTEs |
| Inserts / updates with all columns | Bulk operations (`COPY`, `INSERT ... SELECT`) |
| Mocking is critical (test isolation) | EXPLAIN-tuned hot paths |
| Code-generated typed clients available | Anything where you'd write SQL anyway, then translate to ORM |

**This project**: in Go, `sqlc` (compile-time SQL→typed Go) for everything except trivial CRUD. In Python, `asyncpg` + thin handcrafted queries; SQLAlchemy Core (NOT ORM) when you need composable query building. Avoid ActiveRecord-style ORM (Django ORM, GORM eager loading, SQLAlchemy ORM) — they hide the actual queries until prod.

## N+1 Detection

The single most common performance bug. Detect via:

1. **Logging**: log every query with timing. `SELECT * FROM orders WHERE id = X` repeated 100 times = N+1.
2. **Linting**: `pg_qualstats` extension flags hot patterns.
3. **Test assertion**: `assert query_count(do_thing) <= 5`. Fails the build when N+1 sneaks in.

Fix:

- ORM: eager load (`prefetch_related`, `joinedload`, `JOIN FETCH`, `Includes`).
- Raw SQL: `JOIN` or `WITH ... SELECT ... FROM unnest($1)` for batch lookups.

## Connection Pool Sanity

```
PgBouncer (transaction mode) → Postgres
  ↑
  Application pool (sqlc / asyncpg) — small (10–20 conns per replica)
```

Rules:

- App pool max ≪ Postgres `max_connections`. With PgBouncer in front, you can have 1000 app connections multiplexed onto 50 actual Postgres conns.
- Idle timeout < server idle-in-transaction timeout. Avoid orphaned transactions.
- Per-tenant pool? No. Use one pool, set search_path / RLS policy per request.

## Source Material

- *PostgreSQL Documentation* (16/17/18) — the only canonical source for Postgres specifics. Don't trust Stack Overflow for performance; do trust the docs.
- *Designing Data-Intensive Applications* (Kleppmann) — the storage-and-retrieval chapters are timeless.
- *The Art of PostgreSQL* (Dimitri Fontaine) — practical Postgres patterns.
- Markus Winand — *use-the-index-luke.com* — definitive index reference.
- Brandur Leach — schema migration write-ups (heroku/stripe era).
- Sidekiq author Mike Perham — background-job patterns leveraging Postgres LISTEN/NOTIFY.
