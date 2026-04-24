---
id: TASK-059
title: "Phase O.2.b — Registry export/import for cross-machine sync"
swimlane: core
kind: feature
epic: phase-o
labels: [hub, registry, portability]
status: icebox
priority: P3
appetite: "1d"
created: 2026-04-24
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-059: Phase O.2.b — Registry export/import for cross-machine sync

**Outcome (one sentence):** User can move ~/.coding-os/registry.json between machines via a documented cos registry export/import round-trip.

## Read First
- [cli/registry.py](../../cli/registry.py) — `Registry`, `load_registry`, `save_registry`, `add_project`, existing click group
- [tests/test_registry.py](../../tests/test_registry.py) — fixture pattern for `COS_REGISTRY_PATH` isolation
- [cli/_data_types.py](../../cli/_data_types.py) — `ProjectEntry` dataclass

## Deliverables
1. **CLI `cos registry export [--output PATH] [--portable]`** in `cli/registry.py`:
   - default writes to stdout; `--output` writes to file
   - `--portable` rewrites absolute paths with `$HOME`/`~` placeholders so a dump from `/Users/alice/...` re-imports cleanly on `/Users/bob/...`
   - wire format: same schema as `registry.json` plus `"exported_at": ISO8601` and `"source_host": platform.node()` in the envelope
2. **CLI `cos registry import FILE [--merge] [--dry-run] [--yes]`**:
   - default = REPLACE current registry (after interactive confirm unless `--yes`)
   - `--merge` = union; on slug collision, incoming wins when path differs; no-op when same path; collisions reported on stderr
   - `--dry-run` prints what would change and exits 0 without writing
   - must expand `~` / `$HOME` placeholders then skip entries whose expanded path fails `_looks_like_cos_project`; skip count surfaced in summary
3. **API parity:** `POST /api/hub/registry/export` (returns JSON payload) and `POST /api/hub/registry/import {payload, merge, dry_run}` in `core/web/routes/hub.py` — same rules; dry-run returns the diff without mutating
4. **Tests:** `tests/test_registry_export_import.py` — round-trip on a tmp registry, portable-mode path rewrite, merge collision semantics (same slug+path → no-op; same slug+different path → incoming wins; new slug → appended), dry-run leaves file byte-identical
5. **Docs:** one-paragraph addition to `cli/registry.py` module docstring + CLI `--help` text that cross-references `--portable` behavior

## Acceptance (G/W/T)
- **Given** machine A has 3 registered projects under `/Users/alice/code/*`
- **When** user runs `cos registry export --portable --output reg.json` on A, copies `reg.json` to machine B (home `/Users/bob/`), and runs `cos registry import reg.json --merge --yes`
- **Then** B's registry contains every A entry whose path exists after `~`→`/Users/bob/` substitution; others report `SKIP: path missing on this host` on stderr.

## Verification
- `uv run pytest tests/test_registry_export_import.py tests/test_registry.py -q`
- `uv run pytest tests/test_hub_registry_crud.py -q` (API endpoints)
- Manual round-trip: `cos registry export > /tmp/r.json && COS_REGISTRY_PATH=/tmp/clone cos registry import /tmp/r.json --yes && COS_REGISTRY_PATH=/tmp/clone cos registry list`

## Non-goals
- No Git-backed or cloud sync — explicit push/pull only.
- No per-project state (DBs, hooks) migration — registry.json only; those live inside each project and sync via the user's VCS.

## Work Log
