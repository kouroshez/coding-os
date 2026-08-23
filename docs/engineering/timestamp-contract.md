<!-- domain:CORE | layer:engineering | ssot:true | updated:2026-08-23 -->
# Timestamp Contract — One Representation Per Storage Class

Purpose: Canonical rules for producing, storing, comparing and rendering every timestamp in the kernel, plus the measured compatibility matrix and the per-table legacy reality an agent must look up instead of assume.

Read when: Adding any column, JSON field, state file, log line or log/report reader that carries a time · debugging an "off by 3-4 hours" or "shows yesterday" symptom · reviewing a diff that calls `datetime.*` or `date` in shell.

> Nav: [Section Index](./00-index.md) | [Docs Index](../00-index.md)

## Why this doc exists

A timestamp bug never announces itself. Nothing raises, nothing logs, no test
goes red — the value parses, the row inserts, the page renders. It surfaces
weeks later as *"the dashboard is 4 hours behind"*, *"the daily log says there
are no entries for today"*, or *"the retro window silently drops half the
records"*. This is the exact failure shape [api-contract-discipline](../../src/core/rules/api-contract-discipline.md)
describes — a producer and a consumer that disagree while both keep working —
except the disagreeing field is time, and time has *four* plausible-looking
encodings instead of two plausible-looking names.

The kernel already paid for this once. The docstring on `_parse_iso_ts` in
[observability.py](../../src/core/web/routes/observability.py) records it: using
`time.mktime` as the inverse of `strptime` baked the server's local offset into
a UTC epoch and was *"observed in the wild as a 3-4h drift on the Hub UI when
the server runs outside UTC."* The fix was `calendar.timegm`. The point of this
document is that the next such bug should be unwritable rather than debuggable.

## The contract — three storage classes, one form each

Pick the class by **what the value is for**, then use its single legal form.

| Class | Use it for | Legal form | Producer |
|---|---|---|---|
| **Epoch** | anything compared, sorted, aged, or diffed (TTLs, dwell, cooldowns, heartbeats, `*_at` on hot tables) | `INTEGER` seconds, UTC | Python `now_epoch()` · shell `date +%s` · SQLite `strftime('%s','now')` |
| **Instant** | a moment a human reads back or that crosses a process/tool boundary (log `ts`, envelope stamps, JSON state) | `TEXT` `YYYY-MM-DDTHH:MM:SSZ` — `T` separator, second precision, literal `Z` | Python `now_iso()` · shell `date -u +"%Y-%m-%dT%H:%M:%SZ"` · SQLite `strftime('%Y-%m-%dT%H:%M:%SZ','now')` |
| **Day** | calendar buckets a human names (work-log date headers, `created:` on tasks, `review-by:`) | `TEXT` `YYYY-MM-DD`, **UTC day** | Python `now_day()` · shell `date -u +%Y-%m-%d` |

Three rules bind all three classes:

1. **UTC at rest, always.** Local time is a *rendering*, produced at the edge
   with the viewer's zone and never stored, compared, or sent onward.
2. **Aware or epoch — never naive.** A `datetime` without `tzinfo` is a bug
   waiting for a machine in a different zone; Python will happily treat it as
   local at the first `.timestamp()`, `.astimezone()`, or comparison.
3. **One producer per class.** Do not hand-roll `strftime` at a call site;
   call the helper, so the format has exactly one place to be wrong.

## The measured compatibility matrix

Not a design opinion — this is `uv run python` output on this repo's
interpreter (CPython 3.12.13, SQLite bundled). The four columns are the four
timestamp shapes actually present in `src/` today.

| Producer | Emits | `strptime(…,"%Y-%m-%dT%H:%M:%SZ")` | `fromisoformat` |
|---|---|---|---|
| `now_iso()` — `strftime('%Y-%m-%dT%H:%M:%SZ')` | `2026-08-23T17:49:45Z` | ✅ parses | ✅ **aware**, UTC |
| `.isoformat(timespec="seconds")` | `2026-08-23T17:49:45+00:00` | ❌ `ValueError` | ✅ aware |
| `.isoformat()` | `2026-08-23T17:49:45.640087+00:00` | ❌ `ValueError` | ✅ aware |
| SQLite `datetime('now')` | `2026-08-23 17:49:45` | ❌ `ValueError` | ⚠️ **naive** — silently local on next use |

Read the first column against the third. `logs.py` and `observability.py` both
parse with the strict `%Y-%m-%dT%H:%M:%SZ` form and swallow `ValueError` into
`None`, so **three of the four producers are silently dropped by every reader in
the Hub** — no error, no log, just a record that fails its time filter and
vanishes from the view. That is the whole bug class in one table, and it is why
the Instant form is `Z` and not `+00:00`: `Z` is the only shape both parsers
accept.

The fourth row is the other half. `fromisoformat` on SQLite's `datetime('now')`
returns a **naive** datetime. Every consumer of a `TEXT` time column must
therefore carry the tz-normalizing guard:

```python
dt = datetime.fromisoformat(raw)
if dt.tzinfo is None:                      # SQLite datetime('now') lands here
    dt = dt.replace(tzinfo=timezone.utc)
```

The guard is mandatory and the `if` is load-bearing: a bare
`.replace(tzinfo=timezone.utc)` on a string that *did* carry an offset
**overwrites** it — turning `+03:30` into UTC and moving the instant by 3.5
hours. Use `.astimezone(timezone.utc)` when the value may legitimately carry a
non-UTC offset; use the guarded `.replace()` only to *attach* UTC to a value
already known to be UTC-naive.

## Banned forms — and the legal replacement

| Banned | Why | Use instead |
|---|---|---|
| `datetime.utcnow()` | naive despite the name; deprecated in 3.12, slated for removal | `now_iso()` / `datetime.now(timezone.utc)` |
| `datetime.now()` with no `tz`, when the value is stored or compared | naive local — wrong on any machine outside UTC, and wrong twice a year under DST | `datetime.now(timezone.utc)` |
| `datetime.fromtimestamp(x)` with no `tz=` | renders a UTC epoch in the *server's* zone | `datetime.fromtimestamp(x, tz=timezone.utc)` |
| `datetime.utcfromtimestamp(x)` | naive; deprecated alongside `utcnow` | `datetime.fromtimestamp(x, tz=timezone.utc)` |
| `time.mktime(time.strptime(...))` | treats the parsed UTC struct as local — the documented 3-4h Hub drift | `calendar.timegm(...)` |
| `.replace(tzinfo=utc)` **unguarded** | clobbers a real offset instead of converting | guard with `if dt.tzinfo is None`, or `.astimezone(timezone.utc)` |
| shell `date +%Y-%m-%d` for a stored day | local day — differs from the UTC day for `$(date +%z)` hours out of every 24 | `date -u +%Y-%m-%d` |
| hand-rolled `strftime` at a call site | a fourth format is one typo away | the class helper |

The shell row is not theoretical on this machine. It currently runs `EDT`
(`-0400`), so the local day and the UTC day disagree from 20:00 to midnight
local — **one sixth of every day** — and a reader stamping local while its
writer stamped UTC finds nothing for "today" during that window.

## Legacy reality — look it up, do not assume

The contract above governs everything **new**. It cannot retroactively rewrite
the columns already shipped: [Critical Rule 9](../governance/critical-rules.md)
makes migrations append-only, and unifying live time columns is a migration with
its own task, not a drive-by. So the existing spread is documented here instead,
because the agent's actual failure mode is *assuming* a column's type rather
than checking it.

| Column | Type today | Tables |
|---|---|---|
| `created_at` | `INTEGER` epoch | `graph_nodes`, `graph_edges_v12`, `graph_evidence_v12` |
| `created_at` | `TEXT` — SQLite `datetime('now')`, space-separated, **naive** | `observations`, `task_outcomes`, `learned_patterns` |
| `created_at` | `TEXT` — ISO-Z | `log_events` |
| `updated_at` | `REAL` epoch | `adapter_health` |
| `updated_at` | `INTEGER` epoch | `graph_nodes`, `graph_edges_v12` |
| `updated_at` | `TEXT` | `tasks` (board projection) |
| `started_at`, `completed_at`, `transitioned_at`, `edited_at`, `enqueued_at`, `last_indexed_at` | `INTEGER` epoch | board + graph tables |
| `last_accessed_at`, `last_recalc_at` | `TEXT` | `learned_patterns`, `routing_weights` |

**`created_at` is three different types across one database, and `updated_at` is
three more.** Before you read, write, or compare one of these, confirm the type
at the `CREATE TABLE` — the name tells you nothing.

## Where local time is correct

Two narrow cases, both **rendering or scheduling**, never storage:

- **Display at the edge.** A CLI or Hub view may format an epoch or an Instant
  into the viewer's zone. Convert at the print/serialize boundary; the stored
  value stays UTC.
- **A schedule expressed in local terms.** `launchd`'s `StartCalendarInterval`
  `Hour` is a *local* hour, so `_next_run_at` in [scheduled.py](../../src/core/web/routes/scheduled.py)
  correctly builds a naive-local datetime and `.astimezone(timezone.utc)`s it
  before persisting. Any such site carries a comment saying why the naive value
  is intentional, or the next reader will "fix" it into a bug.

## Enforcement

| Layer | Mechanism |
|---|---|
| Write time | `block-bad-patterns.sh` warns on the banned Python and shell forms |
| CI | `tests/test_timestamp_discipline.py` fails on a banned form in `src/`, and asserts every `now_iso()` copy emits a byte-identical shape |
| Rule | [timestamp-discipline.md](../../src/core/rules/timestamp-discipline.md) — always-active, renders into every scaffold |

`src/core/hooks/_helpers/*.py` keep a local two-line copy of the producer rather
than importing `core.logging_os`, deliberately: the helpers run on the hot hook
path where `cos_say_json.py` documents avoiding that import for latency. The
duplication is permitted **only** because the CI test asserts the copies agree
byte-for-byte with the canonical producer — the format still has one definition,
just several inlined emitters.

## See also

- [api-contract-discipline](../../src/core/rules/api-contract-discipline.md) — the same silent-drift failure shape, on field names
- [state-files.md](state-files.md) — the state files these stamps land in
- [critical-rules.md](../governance/critical-rules.md) — Rule 9 (append-only migrations), Rule 28 (this contract)
