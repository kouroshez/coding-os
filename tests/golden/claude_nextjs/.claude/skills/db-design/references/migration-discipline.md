# Migration Discipline — Zero-Downtime Schema Changes

The patterns for changing schema on a live database. Every migration here assumes:

1. Multiple app replicas running.
2. App version N and N+1 may run simultaneously during deploy.
3. You cannot pause writes.
4. Postgres ≥ 13 (most patterns work back to 9.6).

If you have downtime windows, you can skip half the dance. Document explicitly when an `ACCESS EXCLUSIVE LOCK` operation is acceptable.

## The Two Laws

1. **Forward only.** Migrations don't have a `down()`. Mistakes are fixed by writing a NEW migration that undoes the change. Reversibility encourages laziness; forward-only forces care.
2. **Each release is backward-compatible with the previous one.** App N+1 can run against the old schema. App N can run against the new schema. NEVER both directions broken at once.

## Expand-Contract — the Universal Pattern

Most schema changes follow this three-phase release cycle:

```
Release 1: EXPAND
  - Add new schema (column / table / index) without removing old.
  - App N still uses old; app N+1 (rolled out next) writes BOTH old + new.

Release 2: MIGRATE
  - Backfill data from old → new.
  - App writes both, reads from new (fall back to old if absent).

Release 3: CONTRACT
  - Stop writing to old.
  - Drop old column / table / index after a soak period.
```

Three releases for a rename. Yes, really. Examples below.

## Adding a Column — Easy

Postgres ≥ 11 with no DEFAULT or with a constant DEFAULT: instant. No table rewrite.

```sql
-- Migration v42 — INSTANT, no lock.
ALTER TABLE orders ADD COLUMN coupon_code TEXT;

-- With a constant default (PG 11+) — also INSTANT.
ALTER TABLE orders ADD COLUMN priority SMALLINT NOT NULL DEFAULT 5;
```

⚠️ Volatile DEFAULT (e.g., `NOW()`, function call) DOES rewrite. Use a backfill instead.

## Adding NOT NULL to Existing Column — 3-Phase

Cannot just `ALTER COLUMN ... SET NOT NULL` on a populated nullable column without scanning the whole table.

```sql
-- Phase 1 (release 1): app starts writing the value.
-- Schema unchanged.

-- Phase 2 (release 2): backfill in batches OFFLINE or via background job.
UPDATE orders SET status = 'pending' WHERE status IS NULL;

-- Phase 3 (release 3): now safe to constrain.
-- Use NOT VALID to skip the full-table check at the lock-acquisition moment:
ALTER TABLE orders
    ADD CONSTRAINT orders_status_not_null CHECK (status IS NOT NULL) NOT VALID;
ALTER TABLE orders VALIDATE CONSTRAINT orders_status_not_null;
-- VALIDATE acquires a SHARE UPDATE EXCLUSIVE lock — readers + writers continue.

-- Optional cleanup (release 4): convert CHECK → NOT NULL.
ALTER TABLE orders ALTER COLUMN status SET NOT NULL;
ALTER TABLE orders DROP CONSTRAINT orders_status_not_null;
-- The SET NOT NULL above is now FAST because PG sees the validated CHECK.
```

## Adding a Foreign Key — 2-Phase

```sql
-- Phase 1: add the FK as NOT VALID. Doesn't lock-scan the whole table.
ALTER TABLE order_items
    ADD CONSTRAINT order_items_order_id_fk
    FOREIGN KEY (order_id) REFERENCES orders(id) NOT VALID;

-- Phase 2: validate later (separate migration / background).
ALTER TABLE order_items VALIDATE CONSTRAINT order_items_order_id_fk;
```

## Adding an Index — Always CONCURRENTLY

```sql
-- WRONG — locks writes for minutes on a big table.
CREATE INDEX idx_orders_user ON orders(user_id);

-- RIGHT — no write block, scans + builds in background.
CREATE INDEX CONCURRENTLY idx_orders_user ON orders(user_id);
```

Caveats:

- `CONCURRENTLY` cannot run inside a transaction. If your migration framework wraps each migration in a tx, escape it (e.g., Alembic: `with op.get_context().autocommit_block(): op.execute(...)`)
- Failed concurrent build leaves an INVALID index. Drop and retry: `DROP INDEX CONCURRENTLY IF EXISTS idx_name;`

## Renaming a Column — 3-Phase

```sql
-- Release 1: ADD NEW COLUMN, dual-write.
ALTER TABLE users ADD COLUMN full_name TEXT;
-- App writes BOTH `name` and `full_name`. Reads from `name`.

-- Release 2: BACKFILL + READ from new.
UPDATE users SET full_name = name WHERE full_name IS NULL;
-- App reads `full_name`, falls back to `name` if NULL.
-- App still writes both.

-- Release 3: STOP writing old.
-- App writes only `full_name`. Reads only `full_name`.

-- Release 4: DROP old column.
ALTER TABLE users DROP COLUMN name;
```

Same pattern for renaming a table — three releases at minimum.

## Renaming a Table — 3-Phase via View

Faster alternative:

```sql
-- Release 1: rename + create a view at the old name.
ALTER TABLE legacy_users RENAME TO users;
CREATE VIEW legacy_users AS SELECT * FROM users;

-- Release 2: app updated to use new name.

-- Release 3: drop the view.
DROP VIEW legacy_users;
```

The view is updatable for simple cases. Stops working for complex queries; test thoroughly.

## Dropping a Column — 2-Phase

```sql
-- Release 1: app stops reading + writing the column.

-- Release 2 (after a soak period — at least one full deploy + observation):
ALTER TABLE orders DROP COLUMN deprecated_status;
```

Postgres 11+ marks the column as dropped without rewriting the table; rewrite happens at the next `VACUUM FULL` or `pg_repack`.

## Dropping an Index — Always CONCURRENTLY

```sql
DROP INDEX CONCURRENTLY IF EXISTS idx_orders_old;
```

## Backfills — Batch It

Never run a single `UPDATE` over a billion-row table. The undo log explodes; replicas lag; vacuum can't keep up.

```sql
-- Migration runner: kick off background job, NOT inline.

-- Background worker, in batches of 10k:
DO $$
DECLARE
  rows_updated INT := 1;
BEGIN
  WHILE rows_updated > 0 LOOP
    WITH batch AS (
      SELECT id FROM orders
      WHERE coupon_code IS NULL
      LIMIT 10000
      FOR UPDATE SKIP LOCKED
    )
    UPDATE orders o
    SET coupon_code = COALESCE(o.legacy_promo, '')
    FROM batch
    WHERE o.id = batch.id;

    GET DIAGNOSTICS rows_updated = ROW_COUNT;
    PERFORM pg_sleep(0.1);  -- breathe; let replication catch up
  END LOOP;
END $$;
```

For backfills measured in millions of rows, prefer a dedicated CLI command + checkpoint table that records progress, so re-running picks up where it left off.

## Type Changes — Almost Always Add-and-Migrate

Changing `INT` → `BIGINT` on a wide table rewrites everything. Don't.

Pattern:

```sql
-- Phase 1: add new column with the new type.
ALTER TABLE events ADD COLUMN id_v2 BIGINT;
-- App dual-writes id and id_v2.

-- Phase 2: backfill.
UPDATE events SET id_v2 = id::bigint WHERE id_v2 IS NULL;

-- Phase 3: switch FK targets to id_v2 (per related table).
-- Phase 4: drop id, rename id_v2 → id.
```

## Locking Behavior Cheat Sheet

| Operation | Lock acquired | Blocks |
|---|---|---|
| `ADD COLUMN` (no default or constant default) | `ACCESS EXCLUSIVE` for milliseconds | Everything briefly |
| `ADD COLUMN` (volatile default) | `ACCESS EXCLUSIVE` for table rewrite | Everything for minutes |
| `ALTER COLUMN ... SET NOT NULL` (without prior CHECK) | `ACCESS EXCLUSIVE` for full scan | Everything |
| `ALTER COLUMN ... SET NOT NULL` (with validated CHECK) | `ACCESS EXCLUSIVE` for milliseconds | Briefly |
| `ADD CONSTRAINT ... NOT VALID` | `ACCESS EXCLUSIVE` for milliseconds | Briefly |
| `VALIDATE CONSTRAINT` | `SHARE UPDATE EXCLUSIVE` | DDL only |
| `CREATE INDEX` | `SHARE` | Writes |
| `CREATE INDEX CONCURRENTLY` | `SHARE UPDATE EXCLUSIVE` | DDL only |
| `DROP COLUMN` | `ACCESS EXCLUSIVE` for milliseconds | Briefly |
| `DROP INDEX` | `ACCESS EXCLUSIVE` for milliseconds | Briefly |
| `DROP INDEX CONCURRENTLY` | `SHARE UPDATE EXCLUSIVE` | DDL only |
| `ALTER TABLE ... RENAME` | `ACCESS EXCLUSIVE` for milliseconds | Briefly |
| `TRUNCATE` | `ACCESS EXCLUSIVE` | Everything |

The dangerous ones are the `ACCESS EXCLUSIVE for ... full scan / rewrite` rows. Those are the ones you must dance around.

## Migration Tooling Conventions

Whatever tool you use (Goose, Atlas, Alembic, Flyway, dbmate, sqitch), establish:

1. **One migration per file**, named `NNN_description.sql` (NNN monotonic).
2. **Migrations are append-only** — never edit an applied migration. Mistake → write a new one that fixes it.
3. **Schema dump checked in** — run `pg_dump --schema-only --no-owner` after each migration; commit. PR review then sees the actual end state, not just the diff.
4. **Migrations applied in CI** — every PR runs `migrate up` against a fresh DB. If it fails, build fails.
5. **`SET LOCK_TIMEOUT` on every migration** — fail fast if you can't acquire the lock:
   ```sql
   SET LOCK_TIMEOUT = '5s';
   SET STATEMENT_TIMEOUT = '60s';

   ALTER TABLE orders ADD COLUMN coupon_code TEXT;
   ```
6. **Migrations are idempotent where possible**: `CREATE INDEX IF NOT EXISTS`, `ALTER TABLE ... IF NOT EXISTS COLUMN`, `DROP IF EXISTS`. Re-running a failed migration shouldn't error.

## Per-PR Checklist

Before approving a migration PR, the reviewer asks:

- [ ] Lock duration: which lock, on which tables, for how long?
- [ ] Table rewrite: yes/no? If yes, scheduled for off-hours?
- [ ] Backfill: inline vs background job? Batched? Idempotent? Recoverable?
- [ ] App compatibility: does the previous release still work after this migration applies?
- [ ] Rollback plan: what's the new migration we'd write if this one is wrong?
- [ ] Index added concurrently? Index removed concurrently?
- [ ] `LOCK_TIMEOUT` set?
- [ ] Tested on prod-sized dataset (or at least same shape)?

A "no" without a written justification = block.

## Postgres-Specific Gotchas

- **`SERIAL` columns implicitly create a sequence + DEFAULT + UNIQUE**. Modern code uses `GENERATED BY DEFAULT AS IDENTITY` (cleaner, owns the sequence properly).
- **`CITEXT`** for case-insensitive text is fine but breaks the GIN index pattern. Consider lowercasing in the column itself with a generated column.
- **Generated columns** (`GENERATED ALWAYS AS ... STORED`) are cheap and let you index a derived value. Use for `lower(email)`, JSON extracts, etc.
- **`pg_repack` / `pg_squeeze`** for online table rewrite when you absolutely must. Better than `VACUUM FULL` (which locks).
- **Replication lag**: most patterns assume primary-replica setup. If a backfill is heavy, throttle it (the `pg_sleep(0.1)` above) and watch `pg_stat_replication`.

## Anti-Patterns

1. **Editing a previously applied migration**. Now app version on prod and dev have different schema histories. Tools detect this and refuse to run.
2. **Single-step rename / type change**. Always 3-phase.
3. **`ACCESS EXCLUSIVE` operation in a long transaction**. Holds the lock for the entire transaction. Always one statement per migration when locking.
4. **DEFAULT value backfill via `UPDATE ... WHERE col IS NULL`** on a live large table. Batch + sleep, or use a separate background job.
5. **Concurrent index without `IF NOT EXISTS`** then re-running after failure. Picks up the old INVALID index — drop first.
6. **No `LOCK_TIMEOUT`**. The migration hangs forever waiting for a long-running query, blocking everything new. Always 5–10s default.

## Rollback Reality Check

You don't have one. The "rollback" is "write another migration that undoes". Plan migrations so this is possible:

- Don't `DROP COLUMN` until the column has been unused for a full deploy cycle. The "undo" of a drop is the data — gone.
- Rename via add-and-deprecate, not via in-place rename.
- Test the new code with the OLD schema (CI step: deploy app version N+1 against schema version N). Catches "I forgot to roll out the migration first" bugs.

## References

- [PostgreSQL "Strong Consistency, No SQL" — locking patterns](https://www.postgresql.org/docs/current/explicit-locking.html)
- [Strong's blog — *Safer Postgres migrations*](https://www.thatguyfromdelhi.com/2024/03/safer-postgres-migrations.html)
- [GitLab — *Avoid downtime in migrations*](https://docs.gitlab.com/ee/development/migration_style_guide.html)
- [Stripe — *Online migrations at scale*](https://stripe.com/blog/online-migrations) — the canonical write-up.
- `lock_timeout` reference: <https://www.postgresql.org/docs/current/runtime-config-client.html>
