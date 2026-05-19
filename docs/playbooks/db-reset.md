<!-- domain:CORE | layer:playbooks | ssot:true | updated:2026-05-12 -->
# DB Reset Playbook — Wipe & Rebuild coding-os Data

> P: Canonical procedure for wiping the coding-os runtime state (SQLite + Kùzu + optional agent state) and verifying the auto-rebuild.
> R: An agent or operator needs to reset a corrupted DB, start a clean experiment, or recover from schema drift between deployments.
> S: Single-row corrections (use targeted UPDATE / `cos task-validate`). Don't nuke for a single bad observation.
> N: [docs/engineering/state-files.md](../engineering/state-files.md), [docs/engineering/mcp-fast-path-entry.md](../engineering/mcp-fast-path-entry.md)

> Nav: [Playbooks Index](./00-index.md) | [Docs Index](../00-index.md)

## What gets wiped

| Artifact | Path | What it holds |
|---|---|---|
| SQLite main DB | `.coding-os/coding-os.db` | observations, learned_patterns, tasks index, graph_nodes/edges, retrievals, embeddings, metrics, audit |
| Legacy Kùzu directory | `.coding-os/graph_os.kuzu/` | retired 2026-05-18; `cos db-reset` still removes the dir if a consumer has one left over |
| Agent session state | `.coding-os/<agent>/` | gates, traces, markers (one dir per agent: claude/codex/cursor) |
| Task SSOT (opt-in) | `docs/tasks/TASK-*.md` | Scrumban task files — disk is the source of truth, DB is a derived index |

Default `cos db-reset --confirm` wipes the first **two** only. Use `--wipe-sessions` and `--wipe-tasks` to extend the blast radius.

## When NOT to use this

- A single observation is wrong → `UPDATE observations SET … WHERE id=…;`
- A task file is malformed → `cos task-validate TASK-NNN` and fix the YAML.
- Graph extraction missed a file → `cos graph-reindex --force --path <dir>`.
- Schema drift after a migration was applied → roll the migration forward; never edit a past migration (Rule 9).

A full reset is a last resort. It throws away weeks of memory, retrieval quality signals, and the rolling project trajectory. Even with the backup, restoring is manual.

## Command surface

```
cos db-stats                       # row counts per table, total size — read-only.
cos db-reset                       # DRY RUN — print targets, sizes, populated tables. No writes.
cos db-reset --confirm             # Real wipe. Always backs up first unless --no-backup.
cos db-reset --confirm --wipe-sessions
cos db-reset --confirm --wipe-tasks   # also deletes docs/tasks/TASK-*.md
cos db-reset --confirm --no-backup    # skip backup (NOT recommended)
cos db-reset --confirm --no-reindex   # skip the graph-reindex chase step
```

Backups land at `.coding-os/backups/reset-<YYYYMMDD-HHMMSS>/`. Restore is `cp -r` from there.

## After-the-reset checklist

1. **Restart the agent / MCP server.** The MCP server boots, runs all 27 migrations against the empty (or missing) DB, and recreates every table + index.
2. **Verify the schema** — `sqlite3 .coding-os/coding-os.db "SELECT COUNT(*) FROM sqlite_master WHERE type='table';"` should return ≥ 45.
3. **Task sync** — first agent prompt fires `auto-task-sync.sh` (PostToolUse) which calls `task_sync.sync_tasks` to re-index `docs/tasks/*.md` into the `tasks` table.
   - Manual: `python -m core.thinking_os.task_sync` from the repo root.
4. **Graph rebuild** — `cos graph-reindex` walks the repo, extracts nodes/edges, repopulates `graph_nodes` + `graph_edges_v12` + `graph_evidence_v12`. Without this step the graph stays empty and `cos_graph_*` tools return empty results.
5. **Document chunks (RAG)** — `cos doc-reindex` (or first `cos_doc_search` call) repopulates `document_chunks` + `embeddings`.
6. **Observations / learned_patterns / metrics** — only fill via runtime activity. Expected to start empty.

## What does NOT auto-fill

- `observations` — only written when `cos_observation_record` runs or a hook (e.g. `capture-observation.sh`) fires.
- `learned_patterns` — populated when an observation is promoted; needs activity over multiple sessions.
- `project_trajectory` — populated when `cos_trajectory_snapshot` runs (typically after task-done).
- `session_summaries` — written at session end.

A freshly reset DB is, by design, almost empty until the agent does real work.

## Verification matrix

After a `--confirm` run, check:

```bash
cos db-stats                          # schema present, rows ~0 across the populated set
sqlite3 .coding-os/coding-os.db ".tables" | wc -w   # 45+ tables
cos doctor                                          # health checks all green
cos graph-reindex                                   # then re-run db-stats; graph_* tables populated
```

## Failure modes

- **Backup fails (disk full / permissions)** — command exits 1 before deleting anything. Free space and retry.
- **`cos` not on PATH after wipe** — the wipe doesn't touch the installed `cos` binary; if it's missing, that's a separate install issue.
- **Sub-agent MCP server holds DB lock** — kill stragglers: `pkill -f "thinking_os/server.py"` then retry.

## See also

- [docs/engineering/state-files.md](../engineering/state-files.md) — what lives where
- [docs/engineering/mcp-schema-traps.md](../engineering/mcp-schema-traps.md) — schema after rebuild
- [docs/engineering/graph_os-queries.md](../engineering/graph_os-queries.md) — graph repopulation
