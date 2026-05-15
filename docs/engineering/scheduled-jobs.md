<!-- domain:CORE | layer:engineering | ssot:true | updated:2026-05-06 -->
# Scheduled Jobs

Purpose: Canonical contract for the nightly maintenance pipeline — `src/core/scheduled/nightly.py` — and the optional CRON B agent (Claude Code `CronCreate`).
Read when: Editing `src/core/scheduled/`, `src/core/web/routes/scheduled.py`, or `Makefile` cron targets.
Skip when: Investigating a one-off backfill that doesn't go through the scheduled pipeline.
Read next: [hooks-reference.md](hooks-reference.md), [hub-architecture.md](hub-architecture.md)

> Nav: [Section Index](./00-index.md) | [Docs Index](../00-index.md)

## Why

Learning state (patterns, routing weights) goes stale between sessions. If no session runs for >7 days, `session_enrich.py` never fires `run_decay()`. Patterns with wrong confidence mislead `cos_learn_suggest`. Routing weights drift from actual task outcomes.

Two jobs fix this:

| Job | Mechanism | Needs LLM | Schedule |
|---|---|---|---|
| **CRON A — nightly** | `launchd` plist → Python script | No | Daily 03:00 |
| **CRON B — weekly narrative** | Claude Code `CronCreate` | Yes | Monday 09:00 |

---

## CRON A — nightly.py

Entry point: `src/core/scheduled/nightly.py`

Install: `make cron-install` → writes plist to `~/Library/LaunchAgents/`, loads via `launchctl`.

### Tasks (ordered, per project)

1. **decay** — `run_decay(db_path)` from `src/core/thinking_os/decay.py`
   - Gate: `.last-decay` marker < 7 days → skip (session_enrich already ran)
   - Flock: `fcntl.flock` on marker → prevents double-decay race with session_enrich
   - Output: `{patterns_decayed, patterns_archived, skipped}`

2. **learn_extract** — `learn_extract(conn)` from `src/core/thinking_os/tools/learning.py`
   - Gate: `< 3` task_outcomes → skip; 0 new outcomes since `.last-extract` → skip
   - Idempotent: upsert on `(pattern, domain)` key, `max(confidence)`
   - Output: `{extracted: N, upserted, skipped}`

3. **routing_recalc** — `recalculate_weights(conn)` from `src/core/thinking_os/tools/routing.py`
   - Gate: `routing_drift()` returns no drift → skip
   - Drift defined as: new outcomes added since `outcomes_at_recalc`
   - Output: `{weights_updated: N, skipped}`

### Activity detection

Before any task: `_activity.py::activity_since(db_path, days=1)` checks `observations` and `task_outcomes` for recent writes. Used to gate learn_extract (skip if 0 new outcomes) and CRON B (gate on ≥10 new observations).

### Decision table

| Project state | decay | learn_extract | routing_recalc |
|---|---|---|---|
| DB missing / no tables | SKIP | SKIP | SKIP |
| < 3 outcomes, no session >7d | RUN | SKIP | SKIP |
| ≥ 3 outcomes, inactive >7d | RUN | RUN | if drift → RUN |
| Active (<24h session) | SKIP | SKIP | if drift → RUN |
| All patterns archived | RUN (no-op at floor) | RUN | if drift → RUN |
| Dead >30d, 0 new outcomes | RUN | SKIP | SKIP |

### Multi-project iteration

Reads `~/.coding-os/registry.json` → `projects[].path`. Iterates each project independently. Errors in one project never abort others.

Fallback when registry missing: `COS_PROJECT_ROOT` env → cwd.

### State files

| File | Scope | Purpose |
|---|---|---|
| `<proj>/.coding-os/.last-decay` | per-project | Shared with session_enrich; flock-protected |
| `<proj>/.coding-os/scheduled/.last-extract` | per-project | Idempotency for learn_extract |
| `<proj>/.coding-os/scheduled/last_run.json` | per-project | Full run report; read by hub API |
| `~/.coding-os/scheduled/nightly.log` | global | Rotating log (10 × 100KB) |

### Error handling

- Per-project `try/except` — one failed project never aborts the run
- Per-task `try/except` — one failed task recorded in `last_run.json`, next task runs
- `last_run.json` always written, even on partial failure
- Max 3 consecutive failures → writes `disabled_reason` to `last_run.json`; `cos doctor` surfaces it

---

## CRON B — Weekly Narrative Agent

Mechanism: Claude Code `CronCreate` (user must authorise once via `make cron-b-setup`).

Schedule: `0 9 * * 1` (Monday 09:00 local time).

Gate: ≥10 new `observations` since `last_narrative_at` in `last_run.json`. If gate fails → agent logs skip, no LLM call made.

Prompt contract: agent calls `cos_learn_narrative` for each active project, writes summary to `last_run.json`.

---

## Hub API

`GET /api/scheduled/status` → reads per-project `last_run.json`.

Response shape:
```json
{
  "cron_a": {
    "installed": true,
    "last_run_at": "2026-05-06T03:00:00Z",
    "next_run_at": "2026-05-07T03:00:00Z"
  },
  "projects": [
    {
      "slug": "coding-os",
      "last_run_at": "2026-05-06T03:01:02Z",
      "tasks": {
        "decay":           {"status": "ok",      "patterns_decayed": 3, "patterns_archived": 0},
        "learn_extract":   {"status": "skipped", "reason": "no_new_outcomes"},
        "routing_recalc":  {"status": "ok",      "weights_updated": 5}
      },
      "consecutive_failures": 0,
      "last_error": null
    }
  ]
}
```

---

## Failure / corruption scenarios

| Scenario | Risk | Mitigation |
|---|---|---|
| Double decay (cron + session_enrich same night) | Premature archiving | `fcntl.flock` on `.last-decay`; double-check after lock |
| Two cron processes (manual + launchd) | Race on `last_run.json` | flock on state file before write |
| DB schema < required version | Query fail | Check `get_schema_version()` ≥ 7 before any task |
| Hub registry absent | KeyError / crash | Graceful fallback + log warning |
| learn_extract on empty outcomes | `insufficient_data` | Handled by MIN_DATA_THRESHOLD check inside learning.py |
| Routing recalc with 0 outcomes | No-op | drift check returns False → skipped |
| CRON B with empty observations | Wasted LLM call | Gate: ≥10 new observations check |

---

## Installation

```bash
make cron-install      # install + load launchd plist
make cron-uninstall    # unload + remove plist
make cron-run          # run once now (dry-run safe with DRY_RUN=1)
make cron-b-setup      # print CronCreate invocation for user to approve
```

Plist source: `src/core/scheduled/launchd/com.codingos.nightly.plist.template`.
Installed to: `~/Library/LaunchAgents/com.codingos.nightly.plist`.
