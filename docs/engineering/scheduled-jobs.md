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

1. **decay + consolidate** — `run_decay_locked(db_path, archive_prune_days=...)` from `src/core/thinking_os/decay.py` (the shared throttle+flock wrapper around `run_decay`)
   - Gate: `.last-decay` marker < `decay_throttle_days` (config, default 7) → skip
   - Flock: `fcntl.flock` on marker → prevents double-decay race with session_enrich
   - Consolidation (caps unbounded `learned_patterns` growth, runs every decay):
     - **merge** exact `(pattern, domain)` duplicates — fold losers' `access_count` / `times_validated` into the highest-confidence keeper, delete the rest.
     - **prune** patterns archived in a PRIOR run that are at-floor, lightly-validated (`times_validated < 5`), and dormant > `archive_prune_days` (config, default 90). Deeply-validated archived patterns survive. Pruning runs BEFORE this run's archiving so freshly-archived patterns get a full grace window.
   - Semantic summarisation stays in CRON B (`cos_learn_narrative`) — this is the non-LLM cap.
   - Output: `{decayed, archived, unchanged, working_memory_cleaned, merged, pruned}`

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

### Configurable cadence + responsive extraction

Cadence and thresholds are no longer hardcoded constants. Each project
carries `<proj>/.coding-os/scheduled/config.json`, read by the nightly
daemon, the responsive session-end trigger, and the Hub
(`GET`/`PUT /api/scheduled/config`). `src/core/scheduled/config.py`
owns the schema + validation; missing keys fall back to defaults so an
absent file behaves exactly as before.

| Key | Default | Meaning |
|---|---|---|
| `enabled` | `true` | When `false`, nightly skips every task for the project (decay/extract/routing all SKIP). |
| `hour` | `3` | Desired launchd hour (0–23). Display + `make cron-install` (`COS_CRON_HOUR`); changing it requires a re-install. |
| `decay_throttle_days` | `7` | Replaces the `_DECAY_THROTTLE_DAYS` constant — decay skips if `.last-decay` is younger. |
| `learn_extract_min_outcomes` | `3` | Replaces `_MIN_OUTCOMES` — extract needs at least this many total outcomes. |
| `responsive_extract_threshold` | `5` | Session-end fires `learn_extract` once this many NEW outcomes accrue since `.last-extract`. |
| `archive_prune_days` | `90` | Dormancy window before a prior-run-archived, lightly-validated pattern is hard-deleted by the decay consolidation pass. |

**Responsive extraction** closes the "patterns from today don't exist
until 03:00 tomorrow" lag. The Stop hook `session-end.sh` runs
`scheduled/responsive_extract.py` (bounded, fire-and-forget): it loads
the config, and when `outcomes_since_marker(.last-extract) >=
responsive_extract_threshold` it runs `learn_extract` + touches the
marker — so same-day patterns become available to `cos_learn_suggest`
in the next session without waiting for the nightly daemon. The shared
`.last-extract` marker keeps the responsive path and the nightly path
idempotent (whichever runs first resets the counter). When
`enabled=false` the responsive trigger is a no-op.

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

`GET /api/scheduled/config/{slug}` → `{slug, config, defaults}` — the
editable cadence/threshold config for one project (defaults filled).
`PATCH /api/scheduled/config/{slug}` (body = any subset of the config
keys) → validates + persists via `scheduled.config.save_config`,
returns `{slug, config}`. The Hub **Settings** page renders a
per-project "Scheduled Maintenance" panel against these two endpoints.

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
