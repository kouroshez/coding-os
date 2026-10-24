<!-- domain:DB | layer:reference | ssot:true | updated:2026-06-04 -->
# Query Patterns — Joins, CTEs, Windows, Keyset, Upsert

> P: The concrete query shapes for the common hard cases, each bad→good.
> R: Writing a non-trivial query — aggregation, ranking, pagination, batch write.
> S: Designing the schema/indexes those queries hit — that's [db-design](../../db-design/SKILL.md).
> N: [SKILL.md](../SKILL.md), [reading-explain.md](reading-explain.md)

> Nav: [Skill](../SKILL.md)

## N+1 cures

```python
# Wrong — ORM lazy load: 1 + N queries
for order in session.query(Order).filter_by(user_id=uid):
    print(order.items)          # one SELECT per order

# Correct — eager load in one round trip
session.query(Order).options(selectinload(Order.items)).filter_by(user_id=uid)
```

Raw-SQL equivalent: replace the per-row lookup with a `JOIN`, or batch the keys
into `WHERE id = ANY($1)` (Postgres) / `WHERE id IN (...)` (MySQL) and group in
the app. One query beats a thousand every time.

## CTEs for readability (and the materialization trap)

```sql
WITH recent AS (
  SELECT * FROM events WHERE created_at > now() - interval '7 days'
)
SELECT user_id, count(*) FROM recent GROUP BY user_id;
```

Postgres 12+ inlines a CTE when it's referenced once (no optimization fence).
Pre-12, a CTE was always materialized — a hidden perf cliff. Add `MATERIALIZED`
/ `NOT MATERIALIZED` to be explicit when it matters. MySQL 8 supports CTEs and
recursive CTEs similarly.

## Window functions — rank without a self-join

```sql
-- top 3 orders per user, no correlated subquery
SELECT * FROM (
  SELECT *, row_number() OVER (PARTITION BY user_id ORDER BY total DESC) AS rn
  FROM orders
) ranked
WHERE rn <= 3;
```

`row_number / rank / dense_rank / lag / lead / sum() OVER (...)` replace whole
classes of slow self-joins and app-side loops. Both engines support them (MySQL 8+).

## Keyset pagination (cursor)

```sql
-- page 1
SELECT id, created_at FROM events ORDER BY created_at DESC, id DESC LIMIT 20;
-- next page: pass the last row's (created_at, id) as the cursor
SELECT id, created_at FROM events
WHERE (created_at, id) < ($1, $2)
ORDER BY created_at DESC, id DESC LIMIT 20;
```

Include a unique tiebreaker (`id`) in the ORDER BY so the cursor is total —
otherwise rows with equal `created_at` get skipped or repeated. Needs an index
on `(created_at DESC, id DESC)`.

## Upsert (no read-then-write race)

```sql
-- Postgres
INSERT INTO counters (key, n) VALUES ($1, 1)
ON CONFLICT (key) DO UPDATE SET n = counters.n + 1
RETURNING n;

-- MySQL
INSERT INTO counters (key, n) VALUES (?, 1)
ON DUPLICATE KEY UPDATE n = n + 1;
```

The conflict target must be a unique/PK constraint. Read-modify-write in the app
double-counts under concurrency; the upsert is atomic.

## Bulk insert

One multi-row `INSERT ... VALUES (...), (...), (...)` (or `COPY` / `LOAD DATA`
for thousands) beats a loop of single inserts by 10–100×. Batch in chunks of a
few hundred to a few thousand to bound statement size.
