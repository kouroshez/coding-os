# Doctor Checks — Reference

> Complete list of every `cos doctor` check, grouped by category. Each entry: ID, intent, severity-when-failing, fix hint. IDs are the SSOT — changing one is a breaking change for any consumer parsing JSON output.

Categories: adapter · board · cognition · config · database · docs · graph · hook · hub · mcp · presence · runtime · scaffold · scheduled · stack · state.

Run `cos doctor` for human-grouped text, `cos doctor --format json` for machine ingest.

---

## adapter

### adapter.all_installed_healthy
Every adapter listed as installed in `.coding-os/installed-manifest.json` resolves to a present, hook-complete directory under `<agent_dir>/`.
**Fails** when an entry's adapter dir is missing, mis-rendered, or stripped of hooks.
**Fix**: `bash src/adapters/<agent>/install.sh` for the broken adapter.

### adapter.configured
Active agent's settings file (e.g. `.claude/settings.json`) parses as valid JSON and the declared hooks directory contains every script the registry requires.
**Fails** when settings file is missing, malformed, or hooks dir lacks required scripts.
**Fix**: re-run the adapter installer (`bash src/adapters/<agent>/install.sh`).

### adapter.identity_file_present
`.coding-os/.agent` exists and names a known adapter (claude / codex / cursor).
**Warns** when missing (the dispatcher falls back to env detection but stability suffers).
**Fix**: `echo "<agent>" > .coding-os/.agent`.

### adapter.symlinks_healthy
Per-adapter symlinks under `<adapter_dir>/{rules,commands,skills}` resolve to the meta-repo source.
**Fails** on dangling symlinks (typically: meta-repo moved on disk).
**Fix**: `cos sync-doctor --repair`.

---

## board

### board.config_yamls_valid
Every `scrumban-config.yaml` / `board-config.yaml` parses cleanly and matches the schema.
**Warns** on YAML parse error, **fails** on schema violation.
**Fix**: validate by hand, then `cos board-config --reload`.

### board.frontmatter_valid
Every `docs/tasks/TASK-*.md` parses as lean frontmatter (Rule 14).
**Warns** with a per-file list of offenders.
**Fix**: `cos task-validate TASK-NNN` on each.

### board.index_synced
Legacy `docs/tasks.md` index (if present) matches the file-system reality.
**Warns** on drift; **passes** when no legacy index exists.
**Fix**: `cos task-sync` or delete the legacy index.

### board.no_stale_tasks
No `in_progress` task has been idle past the stale threshold.
**Warns** when a task hasn't seen a worklog append in the configured window.
**Fix**: post a `cos work-log-append` or move the task to `blocked`.

### board.wip_within_caps
Counts in each WIP swimlane stay under their caps from the board config.
**Warns** when a cap is exceeded.
**Fix**: move oldest task out of the offending swimlane.

---

## cognition

### cognition.registries_present
The cognition system finds all role / preset / situation / formula-agent registries it expects.
**Fails** when any registry is missing or fails to load.
**Fix**: `make regen-rules` and confirm `src/core/thinking_os/roles/`, `presets/`, `situations/` are intact.

---

## config

### config.file_present
`.coding-os.yaml` (or equivalent project config) exists and is YAML-parseable at the project root.
**Fails** when missing or malformed.
**Fix**: copy from `src/templates/_base/.coding-os.yaml` and re-customise.

---

## database

### database.openable
`coding-os.db` exists at `$COS_DB_PATH` and SQLite can open it.
**Fails** when missing or corrupted.
**Fix**: `cos brain init` to recreate.

### database.schema_current
`schema_version` table reports the latest migration applied.
**Fails** when at an older version.
**Fix**: `cos brain migrate`.

### database.tables_present
All core tables (`task_outcomes`, `observations`, `embeddings`, …) exist.
**Fails** when any required table is missing.
**Fix**: `cos brain init --force` to apply migrations from scratch.

---

## docs

### docs.agents_md_present
`AGENTS.md` exists at project root (Claude `CLAUDE.md` is a symlink to it for the meta-repo).
**Fails** when missing.
**Fix**: `cos init` or copy from `src/templates/_base/AGENTS.md`.

### docs.markdown_link_integrity
Every relative markdown link under `docs/` and the root README resolves to an existing file.
**Warns** with the list of broken links.
**Fix**: edit the source file to repair the path, or remove the dangling link.

---

## graph

### graph.backend_responsive
The active graph backend (kuzu or sqlite) responds to a probe query.
**Warns** when the backend is offline or slow.
**Fix**: restart MCP, or run `cos graph-reindex` if the index is corrupted.

### graph.cascade_overflow
No graph reindex run has overflowed its budget.
**Warns** when overflow records exist (typically: massive bulk-add).
**Fix**: `cos graph-reindex --force` to rebuild.

### graph.embedding_dimensions
All `embeddings` rows agree on the configured embedding dim.
**Warns** on mixed dims (typically: model swap mid-flight).
**Fix**: `cos brain reindex` after fully migrating to the new model.

### graph.embedding_migration
No embedding migration is currently mid-flight.
**Warns** when one is paused or stalled.
**Fix**: resume or abandon via `cos brain migrate-embeddings`.

### graph.evidence_table
`graph_evidence_v12` table is present (required by current schema).
**Fails** when missing.
**Fix**: `cos brain migrate`.

### graph.freshness
Most-recent graph index is younger than the configured staleness threshold (default 3600s).
**Warns** when stale.
**Fix**: `cos graph-reindex` (or wait for the next auto-reindex hook tick).

### graph.groups_configured
If groups are declared in config, every named group is a valid graph slice.
**Passes** when no groups are configured.
**Fix**: edit `.coding-os/rag-config.yaml::graph.groups`.

### graph.kuzu_state
Kuzu backend directory is either absent (sqlite-only mode) or fully initialised.
**Warns** on a half-built kuzu dir.
**Fix**: `rm -rf .coding-os/graph_os.kuzu` and let auto-fallback handle it, or run the kuzu reindexer.

### graph.legacy_kinds
No graph node uses pre-v16 colon-prefixed `kind` literals.
**Fails** when any legacy kinds remain.
**Fix**: `cos graph-reindex --rebuild-kinds`.

### graph.orphan_symbols
Orphan symbols (no inbound edge) stay within budget (default 5%).
**Warns** when over budget.
**Fix**: `cos graph-reindex --force`, then inspect outliers with `cos graph-query`.

### graph.parse_error_rate
Extractor parse error rate stays within budget (default 1%).
**Warns** when over budget.
**Fix**: check `make verify` output for the offending extractor + file.

### graph.uid_consistency
Every graph node uses the current `src/` prefix convention.
**Fails** when any node carries a pre-src-migration prefix.
**Fix**: `cos graph-reindex --force` to re-extract with the current prefix.

---

## hook

### hook.cos_env_sourced
Every registered hook script `source`s `cos-env.sh` near the top (Rule 3).
**Warns** when any script is missing the source line.
**Fix**: add `source "$(dirname "$0")/cos-env.sh"` to the offender.

### hook.coverage
The hook registry renders cleanly into every adapter declared in `installed-manifest.json`.
**Warns** when a renderer step fails or an adapter capability filter blocks all events for a hook.
**Fix**: `make regen-adapter-templates` and re-run installers.

---

## hub

### hub.consumer_hook_symlinks_healthy
Every registered consumer project's hook symlinks resolve to live meta-repo files.
**Fails** on dangling symlinks (meta-repo moved on disk).
**Fix**: `cos sync-doctor --repair`.

### hub.http_responsive
Hub on port 9188 responds to a health probe.
**Warns** when the hub is down or unreachable.
**Fix**: `cos hub start` (or `cos hub status` to diagnose).

### hub.project_paths_exist
Every registered project path in `~/.coding-os/projects.json` resolves to an existing directory.
**Warns** when an entry points at a missing path.
**Fix**: `cos hub project remove <slug>` for stale entries.

---

## mcp

### mcp.actually_launches
The configured MCP launcher (`cos mcp-start` etc.) runs to readiness without error.
**Fails** with a captured stderr tail when launch fails.
**Fix**: usually a missing `uv` or env var — the failure message names the cause.

### mcp.dispatcher_modules_importable
Every dispatcher module declared in `adapter.yaml::dispatchers` imports cleanly.
**Fails** when any module raises on import.
**Fix**: `uv run python -c "import <module>"` to reproduce, then fix the import.

### mcp.envelope_contract_sample
A sample `cos_*` tool call returns the `ok / fail` envelope (Rule 13).
**Fails** when the envelope is missing or malformed.
**Fix**: ensure `@safe_tool` wraps the offending tool.

### mcp.portable
The MCP launcher works under the agent runtimes declared in adapter.yaml.
**Warns** when a runtime entry probes negative.
**Fix**: see the per-runtime hint in the warning detail.

### mcp.self_test_passes
`python src/core/thinking_os/server.py --test` exits zero.
**Fails** with the captured stderr tail.
**Fix**: run the same command by hand and follow the trace.

---

## presence

### presence.no_zombies
No `.coding-os/<agent>/sessions/*` file points at a PID that exited long ago.
**Warns** when zombie sessions exist.
**Fix**: `cos presence prune` to garbage-collect.

---

## runtime

### runtime.cli_binary_health
`cos --version` resolves to a real binary on `$PATH`, and the editable install is up to date.
**Warns** on stale or unreachable install.
**Fix**: `uv tool install --force --editable . --all-extras`.

### runtime.optional_extras_installed
Optional extras declared in pyproject.toml (rag, graph_os, sdk, …) are importable.
**Warns** with the list of missing extras.
**Fix**: `uv tool install --editable . --all-extras` (or selectively `--extra rag`).

---

## scaffold

### scaffold.boundary_yamls_valid
Every `scaffold-boundary.yaml` under `src/templates/*/scaffold/` parses and references valid paths.
**Warns** on parse error, **fails** on path violation.
**Fix**: validate per template and re-run `make manifest-regen`.

### scaffold.manifest_fresh
`src/core/scaffold_manifest.json` hash matches the live scaffold tree.
**Warns** on drift (typically: editor save without `make manifest-regen`).
**Fix**: `make manifest-regen`.

### scaffold.placeholders_resolved
No scaffold file contains unresolved double-brace template tokens (the substitution syntax used by `cos init`) after rendering.
**Fails** with the list of offenders and their unresolved tokens.
**Fix**: re-run `cos init` (placeholder substitution happens there), or hand-edit the offender.

### scaffold.regen_artifacts_fresh
Derived artifacts (`dimension-registry.md`, `skill-enforcement.md`, `scaffold_manifest.json`, adapter templates) are not older than their source files.
**Warns** when any derived artifact is stale.
**Fix**: `make regen-rules && make regen-adapter-templates && make manifest-regen`.

### scaffold.roots_present
Every directory declared in `src/core/scaffold_manifest.json::roots` exists at the project root.
**Fails** when any root is missing.
**Fix**: `cos init` recreates roots; or copy missing dirs from a sibling scaffold.

---

## scheduled

### scheduled.cron_configured
The scheduled nightly job (decay / GC / compress) is wired into a real cron entry.
**Warns** when not installed, or when too many consecutive failures.
**Fix**: `cos cron install` or inspect `~/.coding-os/scheduled.log`.

---

## stack

### stack.category_balance
Each stack template declares at least one skill per primary category (frontend, backend, etc.).
**Warns** when a category is missing for any stack.
**Fix**: add the missing skill to `src/templates/<stack>/skills/`.

### stack.registry_valid
`src/core/scaffold_manifest.json` and `src/templates/<stack>/stack.yaml` agree.
**Fails** when a stack is referenced but its definition is missing.
**Fix**: `make manifest-regen` after adding/removing a template.

### stack.skills_linked
Every skill referenced by a stack template renders into the consumer's `<adapter_dir>/skills/` tree.
**Warns** with the list of broken symlinks or missing skill defs.
**Fix**: `cos update` or `cos sync-all`.

---

## state

### state.directory_present
`$COS_STATE_DIR` (default `.coding-os`) exists at the project root and is writable.
**Fails** when missing or read-only.
**Fix**: `mkdir -p .coding-os` and ensure permissions allow the runtime user to write.

### state.size_within_budget
`.coding-os/` directory size stays under the configured budget (default 500 MB).
**Warns** when over budget (typically: too many trace JSONLs, unrotated hook log).
**Fix**: `cos brain gc` and `cos presence prune`.

---

## Suppression

Glob-based suppression in `.coding-os.yaml`:

```yaml
doctor:
  ignore:
    - graph.*
    - hook.cos_env_sourced
```

Or one-shot via CLI (repeatable, merged with config):

```bash
cos doctor --ignore 'graph.*' --ignore 'hook.coverage'
```

Suppressed checks are listed in the summary footer: `suppressed: N check(s) via <glob>, ...`.

## Explain

To open this reference inline for a specific check:

```bash
cos doctor --explain hook.cos_env_sourced
```

Prints the matching section and exits 0. Unknown IDs return a hint listing the JSON command that enumerates every valid ID.

## See also

- [src/cli/doctor.py](../../src/cli/doctor.py) — main check definitions
- [src/cli/doctor_graph.py](../../src/cli/doctor_graph.py) — graph-specific checks
- [src/cli/doctor_extras.py](../../src/cli/doctor_extras.py) — runtime + hub + scaffold checks
- [src/cli/doctor_board.py](../../src/cli/doctor_board.py) — board-specific checks
- [docs/engineering/logging_os.md](../engineering/logging_os.md) — the central log helpers `cos doctor` writes through
