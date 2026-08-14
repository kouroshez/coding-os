<!-- domain:META | layer:reference | ssot:true | updated:2026-05-19 -->
# Doctor Checks — Reference

> Complete list of every `cos doctor` check, grouped by category. Each entry: ID, intent, severity-when-failing, fix hint. IDs are the SSOT — changing one is a breaking change for any consumer parsing JSON output.

Categories: adapter · board · bootstrap · cognition · config · database · docs · graph · hook · hub · mcp · presence · runtime · scaffold · scheduled · stack · state.

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
`.coding-os/.agent` exists and names a known adapter (claude / codex).
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

### board.git_tracked
Every DB task row's `docs/tasks/*.md` is git-tracked and committed (board↔git
coherence — the board DB is gitignored, so the `.md` is the only durable
cross-machine SSOT; an untracked completed task vanishes on a fresh clone).
**Warns** with the drifting task ids split into untracked / modified / missing
`.md` (a DB row whose file was never committed). **Passes** when all are clean;
**skips** (pass) when the project is not a git work-tree root.
**Fix**: commit the listed `docs/tasks/*.md` with explicit paths.

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

## bootstrap

Preflight prerequisite checks that run WITHOUT an initialized project:
`cos doctor --bootstrap`. Probe-and-exit mode (like `--otel`) so a brand-new
user can verify the machine before the first `cos init` (TASK-347). README
§ Prerequisites is the min-version SSOT these checks encode.

### bootstrap.python_version
Running interpreter is Python >= 3.10.
**Fails** below the floor.
**Fix**: install a newer Python (`brew install python@3.12` / distro package) and reinstall `cos` with it.

### bootstrap.bash_version
`bash --version` reports major >= 4 (hook scripts use 4.x features; macOS ships 3.2).
**Fails** below the floor or when bash is missing.
**Fix**: `brew install bash` (macOS) / distro package.

### bootstrap.git_present
`git` resolves on PATH (`cos init` runs `git init` + installs git hooks).
**Fails** when missing.
**Fix**: `xcode-select --install` (macOS) / `apt install git`.

### bootstrap.uv_present
`uv` resolves on PATH (updates and extras install through it).
**Warns** when missing — `cos` itself already runs.
**Fix**: `curl -LsSf https://astral.sh/uv/install.sh | sh`.

### bootstrap.sed_flavor
Reports GNU vs BSD sed (adapter installers must work on both).
**Passes** either way — informational detail for support bundles; **warns** only when `sed` is missing entirely.

### bootstrap.hook_parsers
Which of `jq` / `perl` / `python3` the hook layer can use to read its stdin
envelope and extract fields. Both halves degrade (`perl→python3→cat` for the
read, `jq→python3` for the extraction), so `jq` and `perl` are speed, not
capability. **Passes** whenever `python3` resolves; **fails** otherwise, because
with no parser a gate cannot evaluate its input and fails closed on every tool
call — an unusable install rather than a silently unguarded one
([observability-eye § 5 I8](../engineering/observability-eye.md)).

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
The graph backend (SQLite) responds to a probe query.
**Warns** when the backend is offline or slow.
**Fix**: restart MCP, or run `cos graph-reindex` if the index is corrupted.

### graph.cascade_overflow
No graph reindex run has overflowed its budget.
**Warns** when overflow records exist (typically: massive bulk-add).
**Fix**: `cos graph-reindex --force` to rebuild.

### graph.embedding_dimensions
All `embeddings` rows agree on the configured embedding dim.
**Warns** on mixed dims (typically: model swap mid-flight) — this is also the
mixed-model signal after the MiniLM→BGE-M3 cutover, since the two models have
distinct dims (384 vs 1024).
**Fix**: `cos brain reindex` after fully migrating to the new model.

> **Embedding model (M5).** Fresh projects default to `BAAI/bge-m3` — 1024-dim,
> multilingual, ~4.3GB first-time download. The runtime never phones home: the
> model is used offline from the local cache and a vendoring download is
> explicit opt-in via `COS_ALLOW_MODEL_DOWNLOAD=1`. A mixed-dim warn after the
> cutover means MiniLM stragglers remain — re-embed via `make migrate-embeddings`.
> Per-project opt-back to the old small model: `COS_EMBEDDING_MODEL=all-MiniLM-L6-v2`.

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

### hub.code_fresh
A running Hub serves the in-process core (`graph_os`/`web`/`thinking_os`/`board_os`) it imported at start; Python never reloads a live module, so a core edit only reaches projects after a restart.
**Warns** when the newest core `*.py` mtime is newer than the Hub's start (`hub.pid` mtime). **Passes** when the Hub is fresh, not running, or started with `--reload`.
**Fix**: `cos hub restart` (or start with `cos hub start --reload` for a dev auto-reload loop). See `docs/engineering/hub-architecture.md` § Hub serves in-process core.

### hub.consumer_hook_symlinks_healthy
Every registered consumer project's hook symlinks resolve to live meta-repo files.
**Fails** on dangling symlinks (meta-repo moved on disk).
**Fix**: `cos sync-doctor --repair`.

### hub.http_responsive
Hub on port 9188 responds to a health probe.
**Warns** when the hub is down or unreachable.
**Fix**: `cos hub start` (or `cos hub status` to diagnose).

### hub.project_paths_exist
Every registered project path in `~/.coding-os/registry.json` resolves to an existing directory.
**Warns** when an entry points at a missing path.
**Fix**: `cos registry gc` to prune all stale entries (or `cos registry remove <slug>` for a single entry).

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

## Tokens

Token-usage audit of the agent's transcript history: `cos doctor --tokens [--days N]`.
Probe-and-exit mode (like `--otel` / `--bootstrap`) — reads the Claude Code transcript
JSONLs for this project (`~/.claude/projects/<slug>/`), sums the per-turn `usage`
records (input / output / cache-write / cache-read), and reports:

- 7-day (or `--days N`) totals plus a weighted input-equivalent figure
  (in×1 + out×5 + cache-write×1.25 + cache-read×0.1 — the approximate
  usage-limit weighting).
- Average context per API turn (`cache_read / turns`) — the single best
  predictor of burn rate; >200K suggests sessions could use `/compact`
  mid-task or a `/clear` between unrelated tasks.
- Top sessions by cache-read burn, with turn counts — marathon sessions
  (>1,000 turns) are flagged.
- Session-start baseline (median first-turn context) — the fixed overhead every
  session and subagent pays before any work.

**Warns** (in the summary line) when avg context/turn exceeds the budget
(default 200K, override `COS_CONTEXT_BUDGET`). Exits 0 either way — this mode
informs, it does not gate. Supports `--format json` for machine ingest.
Transcripts are agent-runtime-specific; when no transcript directory exists for
the project (e.g. Codex-only usage), the command reports that and exits 0.

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
