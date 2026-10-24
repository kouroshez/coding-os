# Algorithmic Efficiency — the depth behind clean-code §8

The SKILL's §8 carries the non-negotiables. This file carries the reasoning, the
worked shapes, and the mechanics. Read it when a change is hot-path, loops over
unbounded data, or when a reviewer asks "what is `n` here?".

## Why this is a correctness rule, not a nicety

Two engineers implement the same requirement. One returns in 900 ms; the other
takes 20 s. Both pass the same tests, because the tests run on 10 rows and
production runs on 400,000. The difference is not effort or cleverness — it is
one data-structure choice made at write time, for free, by the engineer who
asked "what is `n`?" before typing the loop.

That is the whole point: **the cheap moment to get complexity right is while
writing it.** Afterwards it is an incident, a profiler session, and a refactor
across call sites. This is the runtime sibling of fail-closed error handling —
a slow-enough answer is a failed answer, and at scale its failure mode is
identical to a wrong one (timeout, retry storm, dropped request).

## Step 1 — name `n` before you write the loop

Every loop, comprehension, recursive call, and query has an input size. Name it
out loud, and name its **p99 in production**, not its size in the test fixture.

| What you are iterating | Typical `n` | The trap |
|---|---|---|
| A config file's keys | 10-100 | none — anything is fine |
| Files in a repo subtree | 10³-10⁴ | fine per file; fatal if you re-scan per file |
| Rows from a table | unbounded | the fixture has 5 rows; production has 4M |
| Graph nodes / edges | 10⁴-10⁶ | a nested walk is quadratic on the hub node |
| Log / event stream | unbounded | any full materialization is a memory bug |

If you cannot state `n`, you cannot claim the code is fast enough — only that
it passed a small test.

## Step 2 — hold the complexity budget

| p99 `n` | Acceptable | Reject on sight |
|---|---|---|
| ≤ 100 | anything, including O(n²) | nothing — clarity wins here |
| 10³ – 10⁴ | O(n), O(n log n) | O(n²) |
| ≥ 10⁵ | O(n), O(n log n) | O(n²) unconditionally |
| unbounded / streaming | O(1) memory per item | any `list(...)` of the whole stream |

The left column is the only thing that decides. At `n ≤ 100` a nested loop is
the **right** answer and a hand-rolled index is over-engineering — the budget
cuts both ways.

## Step 3 — the five shapes behind almost every real slowdown

Ranked by how often they actually bite.

### 1. I/O inside a loop (the N+1) — the most common by a wide margin

One query becomes `1 + n` round trips. Each carries fixed latency that no index
can remove, so the cost is `n × RTT` however fast the backend is. Same shape for
HTTP calls, file reads, and subprocess spawns.

```python
# BAD — 1 + n round trips; at n=200 and 5 ms RTT that is a full second of pure waiting
for task in tasks:
    owner = database.fetch_user(task.owner_id)
    rendered.append(render(task, owner))

# GOOD — 2 round trips regardless of n
owner_ids = {task.owner_id for task in tasks}
owners_by_id = database.fetch_users(owner_ids)          # one batched call
rendered = [render(task, owners_by_id[task.owner_id]) for task in tasks]
```

The tell: any `await`, `execute`, `open`, `requests.`, `subprocess.`, or
`fetch(` whose line sits inside a `for`/`while` body. Batch it, or hoist it.

### 2. Membership test against a list inside a loop

`x in some_list` is a linear scan. Inside a loop that makes it quadratic, and it
hides well because the code reads beautifully.

```python
# BAD — O(n × m); at 5k × 5k that is 25 million comparisons
new_users = [user for user in incoming if user.email not in existing_emails]  # a list

# GOOD — O(n + m); one line changed
existing_emails = set(existing_emails)
new_users = [user for user in incoming if user.email not in existing_emails]
```

Same rule in TypeScript: `array.includes(x)` in a loop → build a `Set` first;
`array.find(...)` in a loop → build a `Map` keyed by the lookup field.

### 3. Recomputing a loop-invariant

Anything whose value does not depend on the loop variable belongs above the
loop: compiling a regex, sorting a reference list, reading a config, building a
lookup dict.

```python
# BAD — recompiles the pattern n times
for line in lines:
    if re.match(r"^ERROR \[(\w+)\]", line):
        ...

# GOOD — compiled once
error_pattern = re.compile(r"^ERROR \[(\w+)\]")
for line in lines:
    if error_pattern.match(line):
        ...
```

### 4. Unbounded fetch — pulling everything to use a little

`SELECT *`, `.all()`, `read()` on a whole file, or an unpaginated API call when
the code needs a count, an existence check, or the top ten. Cost is `O(total)`
in time and memory, and it grows with the *table*, not with the feature.

```python
# BAD — loads every row into memory to answer a yes/no question
if len(database.fetch_all_sessions()) > 0: ...

# GOOD — the database answers it
if database.any_session_exists(): ...
```

Push the filter, limit, ordering, and aggregation down to the layer that has an
index for them. Read a large file line by line, never `.read()`.

### 5. Repeated concatenation in a loop

`result += chunk` on a string (or `items = items + [x]`) copies the accumulated
value every iteration → O(n²) bytes moved.

```python
# BAD — quadratic copying
report = ""
for row in rows:
    report += format_row(row)

# GOOD — linear
report = "".join(format_row(row) for row in rows)
```

## Step 4 — measure; never claim a speedup you did not time

A "faster" claim is a factual claim, and this project does not permit unfactual
ones ([test-discipline.md](../../../rules/test-discipline.md) § Run the
deliverable — Critical Rule 26). The same standard applies here:

- **Before optimizing anything non-obvious, measure.** Intuition about where
  time goes is wrong often enough that profiling beats guessing.
- **Report the number, not the adjective** — "180 ms → 12 ms on 50k rows", not
  "much faster".
- **Measure the delivered path.** A micro-benchmark of the inner function can
  improve while the end-to-end command gets slower.

```bash
python -X importtime -c 'import mod'      # import-time cost (CLI startup)
python -m cProfile -s cumtime script.py   # where wall-clock actually goes
py-spy top --pid <pid>                    # sampling a live or hung process
time <command>                            # the honest end-to-end number
```

For a database, read the plan before touching the query: `EXPLAIN ANALYZE`. A
"slow query" is usually a missing index, not badly written SQL.

## Step 5 — accuracy is part of getting it right

Fast and wrong is not an improvement. The precision traps that survive review
because the fixture is too clean:

| Trap | Wrong | Right |
|---|---|---|
| Money in floating point | `0.1 + 0.2 != 0.3` | integer minor units, or `Decimal` |
| Float equality | `if value == 0.3` | compare within a tolerance |
| Unstable sort where ties matter | `sort(key=priority)` | sort with an explicit tie-breaker |
| Integer division truncating silently | `total / count` in an int context | choose `//` or rounding deliberately |
| Naive datetimes | `datetime.now()` | timezone-aware, UTC at the boundary |
| Iteration order assumed | relying on set/dict-hash order | sort explicitly when order is observable |

An "optimization" that changes results is a behavior change, and behavior
changes land as their own commit with their own test — never bundled into a
performance edit.

## When NOT to optimize

This section is the twin of
[anti-overengineering.md](../../../rules/anti-overengineering.md), not an
exception to it. The rule is **don't write the accidentally-quadratic version**
— it is not *micro-optimize everything*.

Reject on sight:

- Rewriting readable code for a gain nobody measured.
- A cache added before a measurement showed the recompute mattered — a cache is
  a correctness liability (invalidation, staleness, memory).
- Hand-rolling what the standard library already does in C.
- Trading a clear O(n log n) for an obscure O(n) at `n = 50`.

The correct instinct: **pick the right data structure while writing, then
stop.** That choice costs nothing and prevents the incident; everything past it
needs a profile to justify it.

## See also

- [clean-code SKILL.md](../SKILL.md) §8 — the non-negotiables and the checklist item.
- [performance SKILL.md](../../performance/SKILL.md) — measuring *deployed* systems: Web Vitals, P95 latency, mobile FPS, profiler tooling.
- [anti-overengineering.md](../../../rules/anti-overengineering.md) — the guard against optimizing what nobody measured.
- [db-design SKILL.md](../../db-design/SKILL.md) — indexes, query plans, and the N+1 at the persistence layer.
