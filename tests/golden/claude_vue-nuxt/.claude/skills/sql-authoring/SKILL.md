---
name: sql-authoring
tier: architecture
domain: [backend, data]
description: Write correct, fast, injection-proof SQL queries — SELECT/INSERT/UPDATE/DELETE, joins, CTEs, window functions, pagination, upserts. Use when writing or reviewing any query, reading an EXPLAIN plan, fixing an N+1, choosing keyset vs offset pagination, or porting SQL between PostgreSQL and MySQL. Covers parameterization (never string-build SQL), set-based thinking, index-aware querying, and plan reading. Triggers — "write a query", "this query is slow", "EXPLAIN", "N+1", "SQL", "optimize the query", "join", "pagination". Pairs with db-design (schema + index DESIGN — this skill is query CRAFT), security-web (injection), backend-fundamentals (data access layer).
globs: ""
paths: []
last_reviewed: "2026-06-04"
versions_ref: versions.json
---

# SQL Authoring

A query is correct, fast, and safe — in that order, none optional. Schema and index *design* belong to [db-design](../db-design/SKILL.md); this skill is the *query* craft: how to express intent so the planner picks an index, how to read the plan when it doesn't, and how to never hand an attacker a string-built statement.

> Read an EXPLAIN plan without eyeballing it:
> `psql -c 'EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) <query>' | python3 scripts/analyze_plan.py`

## Always parameterize — no exceptions

```python
# Wrong — SQL injection; one apostrophe in `name` and the query breaks or leaks
cur.execute(f"SELECT * FROM users WHERE name = '{name}'")

# Correct — the driver binds; the value never touches the SQL text
cur.execute("SELECT * FROM users WHERE name = %s", (name,))
```

String-built SQL is the #1 OWASP injection vector — the server-side rules are owned by [security-web](../security-web/SKILL.md). The query-craft rule: **values are always bind parameters; only identifiers you control (validated against an allow-list) are ever interpolated.** An ORM gives you this for free until you reach for `raw()` — then it's on you.

## Think in sets, not rows

```sql
-- Wrong — N+1: one query per order, 1000 orders = 1001 round trips
SELECT id FROM orders WHERE user_id = $1;          -- then, per row:
SELECT * FROM line_items WHERE order_id = $1;

-- Correct — one query, the join does the work
SELECT o.id, li.*
FROM orders o
JOIN line_items li ON li.order_id = o.id
WHERE o.user_id = $1;
```

N+1 is the most common real-world slowness. It hides behind ORM lazy-loading — `for order in orders: order.items` issues a query per iteration. Fix with a join, a `prefetch`/`selectinload`, or an `IN (...)` batch. Full recipes → [references/query-patterns.md](references/query-patterns.md).

## Index-aware querying (the query's half of the contract)

Index *design* is db-design's job; using one is yours. A query defeats its own index when it:

- wraps the indexed column in a function: `WHERE lower(email) = $1` skips an index on `email` (needs an index on `lower(email)`);
- leads with a wildcard: `LIKE '%foo'` cannot use a b-tree;
- mismatches type: `WHERE id = '42'` (text vs int) may force a cast + seq scan;
- `OR`s across columns the planner can't combine — often better as `UNION`.

When in doubt, read the plan — don't guess. Seq scan on a big table with a selective filter = a missing or unused index. [references/reading-explain.md](references/reading-explain.md).

## Pagination — keyset over offset at scale

```sql
-- Wrong — OFFSET 100000 still scans + discards 100000 rows
SELECT * FROM events ORDER BY created_at DESC OFFSET 100000 LIMIT 20;

-- Correct — keyset: O(log n) seek via the index, stable under inserts
SELECT * FROM events WHERE created_at < $1 ORDER BY created_at DESC LIMIT 20;
```

Offset pagination degrades linearly and double-shows rows when the set shifts. Keyset (cursor) paginates in constant time off the ordering index. Use offset only for small, bounded sets (an admin table's page 3).

## Mutations — upsert, returning, transactions

- **Upsert**: Postgres `INSERT … ON CONFLICT (key) DO UPDATE`; MySQL `INSERT … ON DUPLICATE KEY UPDATE`. Never read-then-write (race).
- **`RETURNING`** (Postgres) hands back the written row in one round trip — no follow-up SELECT.
- Wrap multi-statement invariants in a transaction; keep it short (locks held = contention). `SELECT … FOR UPDATE` to serialize a read-modify-write.

## PostgreSQL vs MySQL (the traps that bite on a port)

| | PostgreSQL | MySQL |
|---|---|---|
| upsert | `ON CONFLICT DO UPDATE` | `ON DUPLICATE KEY UPDATE` |
| returning written row | `RETURNING *` | no `RETURNING` (re-SELECT or `LAST_INSERT_ID()`) |
| string quote | single quotes only; `"x"` = identifier | back-tick identifiers; `"x"` may be a string |
| case sensitivity | identifiers fold lower; data case-sensitive | identifier case depends on OS/`lower_case_table_names` |
| JSON | `jsonb` + GIN index | `JSON` (no partial-key index pre-8.0; functional indexes after) |
| booleans | native `boolean` | `TINYINT(1)` |

Versions pinned in [versions.json](versions.json). Don't assume a feature ports — check.

## Anti-patterns (reject on sight)

- f-string / `+`-built SQL with a runtime value → parameterize.
- `SELECT *` in application code → name columns (stable, index-only scans possible).
- A query in a loop → batch or join.
- `OFFSET` on a large, growing table → keyset.
- `WHERE func(col) = x` against an index on `col` → match the index expression.
- Read-then-write where an upsert/`FOR UPDATE` is correct → race condition.
- Trusting a query is fast without `EXPLAIN ANALYZE` on production-shaped data.

## See also

- [references/query-patterns.md](references/query-patterns.md) — joins, CTEs, window functions, keyset, upsert, N+1 cures.
- [references/reading-explain.md](references/reading-explain.md) — how to read a plan + the `analyze_plan.py` script.
- [db-design](../db-design/SKILL.md) — schema, index, and normalization DESIGN (the other half).
- [security-web](../security-web/SKILL.md) — injection defense (server-side SSOT).
