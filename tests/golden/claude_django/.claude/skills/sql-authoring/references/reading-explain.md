<!-- domain:DB | layer:reference | ssot:true | updated:2026-06-04 -->
# Reading an EXPLAIN Plan

> P: How to read a PostgreSQL plan, what each node means, and the script that summarizes it.
> R: A query is slow, or you want to confirm it uses the index before shipping.
> S: Choosing which index to create — that's [db-design](../../db-design/SKILL.md).
> N: [SKILL.md](../SKILL.md), [query-patterns.md](query-patterns.md)

> Nav: [Skill](../SKILL.md)

## Always ANALYZE on real-shaped data

```sql
EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) SELECT ...;
```

`EXPLAIN` alone shows the planner's *estimate*; `ANALYZE` runs the query and
shows *actual* rows + time. The gap between estimated and actual rows is the
single most useful signal — a 100× gap means the planner is working from wrong
statistics and probably chose the wrong plan. `BUFFERS` shows cache vs disk.

> Never `EXPLAIN ANALYZE` a mutating statement on production without wrapping it
> in a transaction you `ROLLBACK` — ANALYZE *executes* the query.

## Node types, worst → best for a selective filter

| Node | Means | Good when | Bad when |
|---|---|---|---|
| Seq Scan | read every row | tiny table, or you need most rows | big table + selective `WHERE` → missing index |
| Index Scan | walk the index, fetch rows | selective filter | low selectivity (returning most rows) |
| Index Only Scan | answer from the index alone | covering index | — (this is the goal) |
| Bitmap Heap Scan | index → sorted heap fetch | medium selectivity, multiple conditions | — |
| Nested Loop | for each outer, probe inner | small outer × indexed inner | large inputs both sides → use hash/merge |
| Hash Join | build hash, probe | large unsorted joins | tiny inputs (overhead) |

## The three things to check first

1. **Seq Scan on a big table** with a selective `WHERE` → a missing or unused index. Check the filter expression matches an index (no `func(col)`, no type mismatch).
2. **Estimate vs actual row gap** ≥ ~10× → `ANALYZE <table>` to refresh stats, or rethink a correlated predicate the planner can't model.
3. **Nested Loop over thousands** of inner rows → the planner mis-estimated; a hash/merge join is usually cheaper.

## Let the script triage it

```bash
psql -qAtc 'EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) <query>' \
  | python3 ../scripts/analyze_plan.py
```

`analyze_plan.py` walks the JSON plan and emits only the actionable lines (seq
scans on big inputs, estimate misses, risky nested loops) — you read three lines
instead of a 200-line tree. It is offline and DB-free: it only parses the JSON
you pipe in.
