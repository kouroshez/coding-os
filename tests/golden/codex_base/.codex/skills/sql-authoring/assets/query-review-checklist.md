<!-- domain:DB | layer:asset | ssot:false | updated:2026-06-04 -->
# Query Review Checklist

Run before shipping any query that touches a real table.

## Safety
- [ ] Every runtime value is a bind parameter (`%s`/`$1`/`?`) — zero string interpolation of values.
- [ ] Any interpolated identifier is validated against an allow-list (never user input).
- [ ] Multi-statement invariants wrapped in a transaction; read-modify-write uses upsert or `FOR UPDATE`.

## Correctness
- [ ] Joins have the right cardinality (no accidental fan-out duplicating rows).
- [ ] `NULL` semantics handled (`= NULL` is never true; use `IS NULL` / `COALESCE`).
- [ ] Keyset pagination has a unique tiebreaker in `ORDER BY`.
- [ ] Upsert conflict target is a real unique/PK constraint.

## Performance
- [ ] No query inside a loop (N+1) — batched or joined.
- [ ] No `SELECT *` in application code — columns named.
- [ ] Filter expressions match an index (no `func(col)`, no type mismatch, no leading `%`).
- [ ] Large/growing list paginated by keyset, not `OFFSET`.
- [ ] `EXPLAIN (ANALYZE, FORMAT JSON)` run on production-shaped data; `analyze_plan.py` → no unexpected seq scans / estimate misses.

## Portability (if the code targets both engines)
- [ ] Upsert / `RETURNING` / identifier-quoting differences handled (SKILL.md table).
- [ ] versions.json engine versions current (`make skills-check-versions`).
