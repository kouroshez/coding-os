# Timestamp Discipline (Always Active)

> **Hard rule:** UTC at rest, always. Every stored time is one of three forms —
> **epoch `INTEGER` seconds**, **ISO instant `YYYY-MM-DDTHH:MM:SSZ`**, or
> **UTC day `YYYY-MM-DD`** — produced by the class helper, never by a
> hand-rolled `strftime` at the call site. Local time is a *rendering*, made at
> the edge and never stored, compared, or passed on.

Full contract, the measured parser matrix, and the per-table legacy types:
[timestamp-contract.md](../../docs/engineering/timestamp-contract.md).

## Why this is a rule and not a preference

A wrong timestamp format raises nothing. It parses, it inserts, it renders — and
then a filter silently drops the record, or a view reads four hours behind. Both
have already happened here: `time.mktime` baked the server offset into a UTC
epoch (*"3-4h drift on the Hub UI"*, still documented at
`_parse_iso_ts` in `src/core/web/routes/observability.py`), and the strict
`%Y-%m-%dT%H:%M:%SZ` readers in `logs.py` / `observability.py` reject
`.isoformat()` output with a swallowed `ValueError` — the record just disappears
from the view. This is [api-contract-discipline](api-contract-discipline.md)'s
silent-drift shape with time as the contested field.

## Pick the class, then use its one form

| The value is… | Class | Form | Producer |
|---|---|---|---|
| compared / sorted / aged / diffed | **Epoch** | `INTEGER` seconds UTC | `now_epoch()` · `date +%s` |
| read by a human or crossing a process boundary | **Instant** | `YYYY-MM-DDTHH:MM:SSZ` | `now_iso()` · `date -u +"%Y-%m-%dT%H:%M:%SZ"` |
| a calendar bucket (log header, `created:`, `review-by:`) | **Day** | `YYYY-MM-DD` **UTC** | `now_day()` · `date -u +%Y-%m-%d` |

`Z`, not `+00:00`: the `Z` form is the only one both `strptime` and
`fromisoformat` accept, and the Hub's readers use the former.

## Banned — each with its replacement

| Never | Instead |
|---|---|
| `datetime.utcnow()` / `datetime.utcfromtimestamp()` | `datetime.now(timezone.utc)` / `fromtimestamp(x, tz=timezone.utc)` |
| `datetime.now()` with no `tz`, for a value that is stored or compared | `datetime.now(timezone.utc)` |
| `datetime.fromtimestamp(x)` with no `tz=` | `datetime.fromtimestamp(x, tz=timezone.utc)` |
| `time.mktime(time.strptime(...))` | `calendar.timegm(...)` |
| `.replace(tzinfo=utc)` unguarded | guard `if dt.tzinfo is None:`, or `.astimezone(timezone.utc)` |
| `date +%Y-%m-%d` in shell for a **stored** day | `date -u +%Y-%m-%d` |

The unguarded `.replace()` is the subtle one: on a value that already carries an
offset it **overwrites** rather than converts, silently moving the instant.

## Reading a `TEXT` time column

SQLite's `datetime('now')` default yields `2026-08-23 17:49:45` — space
separated and **naive**. Every read of a `TEXT` time carries the guard:

```python
dt = datetime.fromisoformat(raw)
if dt.tzinfo is None:
    dt = dt.replace(tzinfo=timezone.utc)
```

And never assume a column's type from its name: `created_at` is `INTEGER` on the
graph tables, naive `TEXT` on `observations` / `task_outcomes` /
`learned_patterns`, and ISO-Z `TEXT` on `log_events`. Confirm at the
`CREATE TABLE` before you read it — the legacy table is in the contract doc.

## When local time is right

Rendering at the edge (CLI/Hub display in the viewer's zone), and a schedule
genuinely expressed in local terms — `launchd`'s `Hour` is local, so
`_next_run_at` builds naive-local and `.astimezone(timezone.utc)`s before
persisting. Both carry a comment saying so, or the next reader "fixes" them into
a bug.

## Enforcement

`block-bad-patterns.sh` warns at write time · `tests/test_timestamp_discipline.py`
fails CI on a banned form and asserts every `now_iso()` copy emits an identical
shape.

## See also

[timestamp-contract.md](../../docs/engineering/timestamp-contract.md) (full contract + matrix) · [api-contract-discipline.md](api-contract-discipline.md) (same drift shape, on field names) · [clean-code SKILL](../skills/clean-code/SKILL.md).
