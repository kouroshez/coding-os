<!-- domain:ALL | layer:reference | ssot:true | updated:2026-04-20 -->
# Coding OS Development Roadmap

Purpose: Phase-by-phase status of coding-os development, from v0.1.0 through the current v0.3.0.
Read when: Checking what's done, what's planned, or picking up the next piece of work.
Skip when: You need implementation details — go to the corresponding phase plan (`phase-b-rag-plan.md`, `phase-c-task-store-plan.md`, `phase-m-thinking_os-new-formula.md`, `phase-n-role-based-routing-plan.md`).
Read next: The current phase's plan for open work items; [features.md](./features.md) for a cross-cutting system map. Authoritative live status: [../AGENTS.md §Development Status](../AGENTS.md).

## Current State (v0.3.0 — Phases A → N complete)

- **Phase M** — Formula-agents + supervisor + DB v14 + 10 MCP cognition tools + 2 hooks ✅
- **Phase N** — Role-based routing (11 roles = 11 formulas) + TaskSignals + Formula Composer + 12 Presets + 3 MCP tools + connection pool (N.5-A) + preset versioning (N.5-C) + multi-tenant override (N.5-E) ✅
- **Phase N.6** — Behavioral tracing: `core/thinking_os/tracing.py` + 5 instrumented MCP tools + `cos cognition trace` CLI + [HTML replay viewer](cognition-trace-replay.html) + 10 behavioral tests ✅
- **Deferred (post-usage-data)**: N.5-B metrics observability · N.5-D circuit breaker · N.5-F rate-limit semaphore on `cos_graph_impact`.

## Historical (v0.1 → v0.2 sections below preserved verbatim)

### Done — v0.1.0 (initial release)

- [x] Core thinking_os MCP server (18 tools, cos_* prefix)
- [x] Core hooks (20 scripts, parameterized via cos-env.sh)
- [x] Core rules (thinking_os.md, memory.md)
- [x] Core skills (thinking_os, clean-code, codebase-explorer)
- [x] Claude adapter (settings.template.json, install.sh)
- [x] Codex adapter (hooks.template.json, install.sh)
- [x] CLI (init, add-adapter, health, eject)
- [x] Django template (python-django skill)
- [x] Next.js template (nextjs-react, frontend-design skills)
- [x] Base template (AGENTS.template.md, coding-os.yaml.template)
- [x] Documentation (architecture, getting-started)

### Done — Phase 1 (v0.1.1 critical fixes)

- [x] Fixed missing `import os` in `record_outcome.py` and `record_review.py`
- [x] Agent-agnostic rewrite of `test-hooks.sh` (replaced hardcoded `.claude/` with `$COS_STATE_DIR`)
- [x] Verified `verify-agent-system.sh` is already agent-agnostic
- [x] Renamed Python function names `nako_*` → `cos_*` in server.py

### Done — Phase 2 (testing infrastructure)

- [x] CLI integration tests (`tests/test_cli.py` — 28 tests)
- [x] Hook parameterization tests (`tests/test_hooks.py` — 24 tests)
- [x] Cross-adapter installation tests (`tests/test_adapters.py` — 21 tests)

### Done — Phase A (template completion)

- [x] Generic governance + foundation files in `templates/_base/scaffold/docs/` (16 files: governance, PRD/architecture/api-contracts/ops indexes, foundation-map, roadmap, workflow-guide, task templates)
- [x] Django stack overlay (`templates/django/scaffold/docs/`): 3 playbooks + 6 engineering rules copied from NakoDigital production docs
- [x] Next.js stack overlay (`templates/nextjs/scaffold/docs/`): 3 playbooks + 6 engineering rules + 4 design system files + pages-content-spec
- [x] CLI overlay logic + AGENTS.md placeholder substitution (19 placeholders, multi-template merge)
- [x] `docs-lint.sh`, `docs-nav-fix.sh` scripts + `make docs-lint`/`docs-nav-fix`/`ref` targets
- [x] Task detail template aligned with NakoDigital structure (9 sections + DOMAIN_REFS marker)
- [x] 38 new scaffold tests in `tests/test_template_scaffold.py`

### Done — Phase B (RAG integration)

- [x] **B.1** — `core/thinking_os/embeddings.py` foundation: lazy model loading, cosine similarity, upsert/search/reindex with graceful degradation when `sentence-transformers` is unavailable
- [x] **B.1** — Migration v5: `embeddings` + `document_chunks` tables with indexes and unique constraints
- [x] **B.1** — `[rag]` optional dependency group in `pyproject.toml` (sentence-transformers + numpy)
- [x] **B.1** — 47 unit tests in `test_embeddings.py` + 11 migration tests in `test_db.py`
- [x] **B.2** — Inline embedding in `capture.py` and `tools/learning.py` (observations, learned_patterns, outcome_history) with fire-and-forget pattern
- [x] **B.2** — `make cos-reindex` Make target for bootstrap/model upgrade
- [x] **B.2** — 7 integration tests verifying embedding side effects
- [x] **B.3** — `core/thinking_os/doc_indexer.py`: heading-aware markdown chunker (H2/H3 + paragraph windowing fallback), mtime-based incremental indexing, orphan cleanup
- [x] **B.3** — `templates/_base/scaffold/.coding-os/rag-config.yaml` with 8 source types and project-level excludes
- [x] **B.3** — `make docs-index`/`docs-reindex` Make targets
- [x] **B.3** — 32 tests in `test_doc_indexer.py`
- [x] **B.4** — `core/thinking_os/tools/docs.py::doc_search` with priority boost and per-source dedupe
- [x] **B.4** — New MCP tool `cos_doc_search` registered in `server.py` (now 19 cos_* tools)
- [x] **B.4** — `cos_health` extended to report RAG status (embeddings_available, model name, counts)
- [x] **B.4** — 14 tests in `test_doc_search.py`
- [x] **B.5** — `memory_search` augmented with semantic blended scoring (50/50 blend when embedding hit, pure 5-signal otherwise)
- [x] **B.5** — Semantic-only hits hydrated and merged into result list, source label updated to `fts5+semantic`
- [x] **B.5** — 9 tests covering blend formula, synonym match, FTS5 fallback, semantic-only hits
- [x] **B.6** — `make cos-download-model` for offline-friendly first-run setup
- [x] **B.6** — Hook `block-protected-files.sh` updated to allow scaffold paths
- [x] **B.6** — Roadmap and architecture docs updated

**Phase B totals: 3 new modules, 1 new MCP tool, ~109 new tests.**

**Total test count after Phases 1-2 + A + B: 639 passing, 3 pre-existing unrelated failures.**

### Done — Phase C (hybrid task store)

- [x] **C.1** — Migration v6: `tasks` table with 17 columns (task_id PK, title, domain, status, file_path, content_hash, mtime, goal_text, scope_in/out, requirements, dependencies, source_of_truth, read_first, open_questions, rabbit_holes, verification), 3 indexes on status/domain/file_path, `has_tasks_table(conn)` helper
- [x] **C.1** — 8 migration tests in `test_db.py` (all pass)
- [x] **C.2** — `core/thinking_os/task_parser.py` (~380 LOC): pure stateless parser, immutable `ParsedTask` dataclass, handles all 9 section types, tolerates missing sections, front-matter stripping, H1 task_id extraction, dependency refs with word-boundary matching
- [x] **C.2** — 43 pure unit tests in `test_task_parser.py` including end-to-end fixture from real NakoDigital TASK-199 (all pass without rag extras)
- [x] **C.3** — `core/thinking_os/task_sync.py`: mtime-incremental sync, status-only fast path (`sync_status_only`), orphan cleanup for deleted files, embedding integration via Phase B pipeline, archive/ subdirectory skip, graceful degradation
- [x] **C.3** — 28 tests in `test_task_sync.py` (all pass)
- [x] **C.4** — `core/thinking_os/tools/tasks.py`: 4 query functions (task_by_filter, task_dependencies, task_dependents, task_search), semantic search with LIKE fallback, quoted-JSON dependency matching to prevent TASK-19 vs TASK-195 false positives
- [x] **C.4** — 32 tests in `test_task_tools.py` (all pass)
- [x] **C.5** — 4 new MCP tools registered in `server.py`: `cos_task_search`, `cos_task_dependencies`, `cos_task_dependents`, `cos_task_by_filter`. Tool count now **21**
- [x] **C.5** — `cos_health` extended with `task_store.tasks_count`
- [x] **C.5** — MCP stdio protocol verified end-to-end: all 4 new tools visible in `tools/list`, callable via `tools/call` with real JSON-RPC
- [x] **C.6** — Auto-sync hooks wired into `task-start.sh` (full sync), `task-done.sh` (status-only fast path), `task-create.sh` (full sync). Fire-and-forget — never blocks the agent.
- [x] **C.7** — `make task-sync` / `task-resync` Makefile targets with `$(CURDIR)` path resolution so they work regardless of `uv run --directory`
- [x] **C.7** — End-to-end verification on real NakoDigital 240 tasks: all indexed successfully, dependency graph correct (TASK-195 → 8 real dependents including TASK-199 commission model, TASK-216 multi-vendor splitting), semantic search finds the right tasks for "payment splitting multi vendor revenue", substring safety test passes (TASK-019 does not match TASK-195)

**Phase C totals: 3 new modules, 4 new MCP tools, 1 new Makefile target, 111 new tests, 3 auto-sync script hooks.**

**Total test count after Phases 1-2 + A + B + C: 750 passing, 3 pre-existing unrelated failures. MCP tools: 21.**

**Real-world verification:** `scripts/verify-phase-c-e2e.sh` (inline Python harness) confirms the full pipeline works on NakoDigital's 240-file production task corpus.

### Done — Phase D (CLI UX + upgrade path + packaging) — v0.2.0

Phase D turned the core into a distributable product. Six incremental sub-phases, each shippable in isolation.

#### D.1 — Bug fixes + SSOT foundation

- [x] **B1 fix** — stack-specific skills now auto-linked into the agent's `skills_dir` after `cos init`/`cos add-stack`. Regression: before D.1, `python-django`/`nextjs-react`/`frontend-design` were silently missing from `.claude/skills/` even though templates declared them.
- [x] New helper `core/scripts/link-stack-skills.sh` — agent-agnostic, reusable from Make targets and `cos update`.
- [x] New CLI subcommand `cos server-start` — portable MCP wrapper. `.mcp.json` no longer hardcodes absolute paths; the `cos` binary on PATH resolves the server location at runtime.
- [x] `.coding-os.yaml.verify` auto-populated from aggregated stack `VERIFY_*` substitutions (backend / frontend / docs keys).
- [x] Doctor checks **C13** `stack_skills_linked` (fails when the B1 regression reappears) and **C14** `mcp_portable` (warns on hardcoded path).
- [x] `adapter.yaml.commands_dir` field + Python dataclass + schema — removes the last `if agent == "claude"` in cli code (SSOT guard test now passes).

#### D.2 — Interactive init + idempotent detection

- [x] `cos init` prompts for missing `--agent` / `--template` / `--name` when a TTY is attached (or piped input is provided).
- [x] `--agent` accepts comma-separated values (`-a claude,codex`) — installs multiple adapters in a single init.
- [x] `--yes` flag for strict non-interactive CI runs.
- [x] Safe-prompt helper — piped stdin without answers silently falls back to defaults instead of aborting (preserves all flag-based tests).
- [x] `_detect_existing_install()` + `_sync_missing()` — re-running `cos init` in an already-initialized project offers to sync missing components instead of overwriting.

#### D.3 — `cos update` (upgrade path)

- [x] New command `cos update` — builds target asset manifest from current coding-os + existing project manifest, computes diff, applies.
- [x] `--dry-run` shows the diff without writing.
- [x] `--format json` for scripting; `--force` to re-link everything.
- [x] Orphan cleanup — asset removed upstream → symlink removed from project.
- [x] Scanner filters to symlinks only → user-ejected copies and path-scoped stack rules never get flagged as orphans.
- [x] `installed-manifest.json` snapshot written to `.coding-os/` after each `cos init`/`cos update`.
- [x] DB migrations run automatically (idempotent — skips already-applied versions).
- [x] Non-destructive: never touches `docs/`, `AGENTS.md`, `.coding-os.yaml` user fields.

#### D.4 — `cos setup` (docs bootstrap)

- [x] New command `cos setup` — three modes: `interactive` (4-question wizard), `import-prd` (pure-regex parser + keyword classifier), `skip` (no-op pointer).
- [x] PRD classifier with 11 targets + `99-misc.md` fallback. No LLM call — deterministic keyword routing.
- [x] Splits H2 sections from a source PRD, groups by classifier, writes to `docs/PRD/NN-*.md`.
- [x] `make docs-index` runs automatically after write (best-effort).
- [x] Idempotent — existing PRD files are skipped, never overwritten.

#### D.5 — `cos eject-file` (fine-grained customization)

- [x] New command `cos eject-file <path>` — replaces a single symlink with a writable copy.
- [x] `cos update` ignores regular files → ejected files stay customized across upgrades.
- [x] Paired test for "edit after eject does not affect source" — proves isolation.

#### D.6 — Distribution via `uv tool install`

- [x] `pyproject.toml` v0.2.0 with `[project.scripts] cos = "cli.main:cli"`.
- [x] `uv tool install --editable .` verified end-to-end — `cos` binary appears in `~/.local/bin/` and works from any cwd.
- [x] CLI `--version` returns "0.2.0".
- [x] Full wheel packaging with bundled `core/` / `templates/` data files is deferred to v0.3 — editable install is the blessed path for v0.2.

**Phase D totals: 3 new CLI commands (update, setup, eject-file) · 1 new CLI subcommand (server-start) · 2 new doctor checks · 1 new adapter field (commands_dir) · ~50 new tests.**

**Test count after Phases 1-2 + A + B + C + D: 985 passing, 0 failing. CLI commands: 16.**

### Done — Phase E (enterprise hook regime + docs-first principle) — v0.2.1

Phase E turns the hook layer from "a few blockers" into an enterprise-grade guardrail that makes agent mistakes visible at edit time instead of CI time. Six new hooks + one Python helper + one task-start enhancement.

#### E.1 — Docs-first enforcement (the highest-impact hook)

Problem: agents would implement features from scratch without consulting any doc. Code shipped, but no one knew *which spec it implemented*.

Solution:

- [x] `task-start.sh` now parses the active task file's **Source of Truth** and **Read First** sections and writes `$COS_STATE_DIR/.doc-anchor` (session-scoped, with task ID prefix).
- [x] New hook **`enforce-doc-anchor.sh`** (PreToolUse Write/Edit on code files): BLOCKS any code write until `.doc-anchor` is populated with non-placeholder paths.
- [x] Exemptions: `*/tests/`, `*/docs/`, `*/scaffold/`, `*/migrations/`, `.coding-os/.claude/.codex/`; CLEAR 1 gate; task names containing `exploratory|spike|experiment|scratch|governance|docs-update`; one-shot `$COS_STATE_DIR/.doc-anchor-override`.
- [x] Task template (`docs/governance/templates/task-detail.md`) now marks Source of Truth as REQUIRED with a note explaining the anchor contract.
- [x] CLAUDE.md Rule 0 added at the top (docs-first principle is the highest-priority rule).

#### E.2 — Migration version guard (catastrophic prevention)

- [x] New hook **`block-migration-conflict.sh`** (PreToolUse Write/Edit): scans diffs of `db.py` for `MIGRATIONS.append((N, ...))` lines, blocks duplicate `N` values. Also catches framework-style collisions (`0003_foo.py` next to existing `0003_bar.py`).
- [x] CLAUDE.md Rule 10 extended to mention the hook.

#### E.3 — `uv run ... <<` heredoc blocker (agent-specific)

- [x] New hook **`block-uv-heredoc.sh`** (PreToolUse Bash): detects `uv[[:space:]]+run[^|&;]*<<` pattern — the exact shape that hangs silently per CLAUDE.md Rule 9. Error message includes the canonical "write a Python file" workaround pattern.

#### E.4 — Generated-artifact drift (regen reminder)

- [x] New hook **`regen-reminder.sh`** (PostToolUse Write/Edit):
  - `templates/*/stack.yaml` → remind `make regen-rules` + `make manifest-regen`
  - `adapters/*/adapter.yaml` → remind `make manifest-regen`
  - `templates/**/scaffold/**` → remind `make manifest-regen` + `capture_golden.py`
  - Hand-edit to `core/rules/dimension-registry.md` or `.../skill-enforcement.md` or `core/scaffold_manifest.json` or `tests/golden/**` → WARN "this is generated, edit the source instead"
- [x] CLAUDE.md Rule 11 added documenting the regen matrix.

#### E.5 — Hardcoded-literal front guard

- [x] New hook **`block-hardcoded-literals.sh`** (PreToolUse Write/Edit on `cli/*.py`) + Python helper **`core/scripts/check_hardcoded_literals.py`**: scans diff content for quoted stack/adapter IDs (`"django"`, `"claude"`, `"python-django"`). Data-driven — reads forbidden list from `templates/*/stack.yaml::id` and `adapters/*/adapter.yaml::id`.
- [x] Comment lines and docstrings allowed. Literals in `tests/` and outside `cli/` also allowed.
- [x] Pairs with existing test-time guard (`test_no_hardcoded_stacks`) so the offending edit never lands on disk.
- [x] CLAUDE.md Rule 12 added.

#### E.6 — Test-first reminder

- [x] New hook **`test-first-reminder.sh`** (PostToolUse Write/Edit): after code edit on `.py/.ts/.tsx/.js/.jsx`, finds the sibling test file (`test_<name>.py`, `<name>.test.ts*`, `<name>.spec.ts*`). Prints its path OR suggests one if none exists. Never blocks.

#### Wire-up + SSOT propagation

- [x] `adapters/claude/settings.template.json` — Bash PreToolUse now has 4 hooks (added `block-uv-heredoc`); Write/Edit PreToolUse has 11 hooks (added `block-migration-conflict`, `block-hardcoded-literals`, `enforce-doc-anchor` in correct order); PostToolUse Write/Edit has 5 hooks (added `regen-reminder` + `test-first-reminder`).
- [x] `core/scaffold_manifest.json` regenerated (10 sections, 763 files — up from 703).
- [x] All 10 golden fixtures regenerated to match the new hook set.

#### Tests

- [x] `tests/test_hooks_phase_e.py` — **35 tests** covering every hook: block path, allow path, exempt path, escape hatch. All pass.

**Phase E totals: 6 new hooks, 1 new Python helper, 1 task-start enhancement, 3 CLAUDE.md rules, 1 task-template section change, 35 new tests. Cumulative hook count: 27 (was 22).**

### Done — Phase F (MCP visibility + workflow integrity) — v0.2.2

Phase F addresses the invisible failure modes that bit us during Phase D/E development — MCP silently dead, capture hook failing without signal, zero observations persisted for entire sessions. Four new hooks, one existing hook hardened, one new doctor check (C15), one Makefile simplification.

#### F.1 — Replace `make dogfood-sync` with `make dogfood`

- [x] Removed the narrower `dogfood-sync` target (only rendered `.claude/settings.json`) — it was a subset of `adapters/claude/install.sh` and caused the real MCP break (it skipped re-rendering `.mcp.json`).
- [x] New `make dogfood` target is a one-line wrapper around `bash adapters/claude/install.sh` — single canonical path for re-rendering the whole `.claude/` + `.mcp.json` from the template. Dogfooding via the exact same install script user projects use.

#### F.2 — Hardened `capture-observation.sh`

- [x] Background `python3 capture.py` invocation now appends stderr to `$COS_STATE_DIR/.capture-errors.log` instead of `2>&1 &`-redirecting it to `/dev/null`. Silent failures now leave a paper trail the Stop hook surfaces.

#### F.3 — `warn-mcp-down.sh` (SessionStart)

- [x] New hook: at session start reads `.mcp.json`, launches the declared command with an initialize handshake (5s timeout), prints a loud banner to stdout+stderr if the server is unreachable. Exempt when no MCP is registered.
- [x] Wired into both `startup` and `compact|resume` SessionStart matchers.

#### F.4 — `check-capture-worked.sh` (Stop)

- [x] New hook: at session end, queries `observations` table for rows with current `session_id`. Zero-count → warn. Reads `.capture-errors.log` and surfaces the last 3 errors. Truncates the error log for the next session.

#### F.5 — `enforce-memory-check.sh` (PreToolUse Write|Edit)

- [x] New hook: blocks code writes on `.py/.ts/.tsx/.js/.jsx/.go/.rs/.rb` unless `$COS_STATE_DIR/.memory-check` is populated (agent recorded a `cos_search` call during Orient).
- [x] Exemptions: CLEAR 1 gate; exploratory/spike/governance/docs-update task names; tests/migrations/scaffold/docs paths; `.memory-check-override` one-shot bypass.
- [x] Error message gives three repair paths (do the memory check, classify as CLEAR 1, mark task exploratory) so the agent never gets stuck without a clear way forward.

#### F.6 — `remind-learn-validate.sh` (PostToolUse Bash)

- [x] New hook: fires only on `(make|cos) task-done` commands. Reads `$COS_STATE_DIR/.learn-suggestions` (written by Orient's `cos_learn_suggest`), prints a concise reminder listing each pattern the agent saw, with a call to `cos_learn_validate(pattern_id, was_helpful)`. Clears the suggestions file after printing (next task starts clean).

#### F.7 — Doctor check C15 + regression tests

- [x] New `_check_mcp_actually_launches` in `cli/doctor.py`: replays the exact Claude Code launch path against `.mcp.json`, with a real initialize handshake. PASS only when the server responds; FAIL with the actual stderr tail and a pointed repair path (especially for the `uv run --directory` → "unable to open database file" pattern that bit us in real life).
- [x] Regression tests in `tests/test_hooks_phase_f.py::TestDoctorC15Regression`:
  - missing `.mcp.json` → FAIL
  - hardcoded `uv run --directory` form → FAIL (the historical break)
  - nonexistent command → FAIL
  - wrapper form (`cos server-start`) → PASS

#### F.8 — `cos server-start` portability fix

- [x] `cli/main.py::server_start` now captures the caller's cwd BEFORE `uv run --directory` chdirs into the server tree and injects `COS_DB_PATH` + `COS_STATE_DIR` as env vars — so the server resolves `.coding-os/coding-os.db` against the actual project root, not against the server source tree. Uses `os.execvpe` to pass env through the exec.

#### Wire-up

- [x] `adapters/claude/settings.template.json` — 29/29 hook entries with `statusMessage` (Phase D/E finished statusMessage coverage; Phase F added 4 new entries and fixed one structural bug). All UI indicators emoji-prefixed for quick visual scan.
- [x] Regenerated `core/scaffold_manifest.json` (10 sections, 803 files — up from 763) and all 6 golden fixtures.

#### Tests

- [x] `tests/test_hooks_phase_f.py` — **22 tests** across 5 test classes (warn-mcp-down, check-capture-worked, enforce-memory-check, remind-learn-validate, DoctorC15Regression). All pass.

**Phase F totals: 4 new hooks, 1 hardened hook, 1 new doctor check, 1 CLI portability fix, 1 Makefile simplification, 22 new tests. Cumulative hook count: 33 (was 27).**

### Done — Phase G (hook registry manifest + meta-hooks + visibility) — v0.2.3

Phase G eliminates template drift between Claude and Codex by making `core/hooks/registry.yaml` the single source of truth. Adds 4 meta-project hooks that protect the mother-project from its own development drift, plus a visibility layer (`.hooks.log`, `cos hooks-log`, `cos hooks-list`) so humans and agents can *see* hooks fire in real time.

#### G.1 — Hook Registry Manifest (SSOT for registrations)

- [x] New file `core/hooks/registry.yaml` — one entry per hook with {id, script, description, category, phase, events[{event, matcher, status_message}], optional timeout}.
- [x] New section `hook_capabilities` in `adapters/<id>/adapter.yaml` declaring which {event, matcher} pairs each adapter can actually trigger.
- [x] New module `cli/hook_renderer.py` reads registry + capabilities, renders adapter-specific template files deterministically.
- [x] New make target `make regen-adapter-templates` drives the renderer.
- [x] `adapters/claude/settings.template.json` and `adapters/codex/hooks.template.json` are now **generated** (never hand-edit). Listed as derived artifacts in AGENTS.md.

Result: adding a hook = **1 YAML entry + 1 regen command**. Drift between Claude and Codex templates is now **impossible by construction**.

#### G.2 — Hook activity log + visibility CLI

- [x] `core/hooks/cos-env.sh` now exports `cos_log_hook()` helper + `COS_HOOK_LOG` path (default `.coding-os/.hooks.log`). Auto-truncates past 4000 lines.
- [x] Every key hook (capture-observation, session-context, session-end, the 4 new meta-hooks) calls `cos_log_hook <name> <fire|ok|warn|error|reminded|override-used>` on entry and decision points.
- [x] New `cos hooks-log [-n N] [--follow]` command tails the log.
- [x] New `cos hooks-list [--agent X] [--category Y] [--phase Z]` reads the manifest and filters.

Result: users and agents can *see* hooks fire. If `cos hooks-log` shows zero entries, the agent runtime isn't delivering the event (usually stale settings.json needing reload).

#### G.3 — Four meta-project hooks (category: meta)

- [x] **`check-agents-md-size.sh`** (PostToolUse Write|Edit on AGENTS.md) — warns at 28 KiB, errors at 32 KiB (Codex's read cap).
- [x] **`check-agents-md-refs.sh`** (PostToolUse Write|Edit on AGENTS.md, core/rules/, core/skills/) — flags dangling path references.
- [x] **`remind-dogfood.sh`** (PostToolUse Write|Edit on core/** and adapters/**) — meta-project-only reminder to run `make dogfood-full`. 10-minute debounce. Detects meta-project by the presence of templates/_base + both adapter dirs.
- [x] **`warn-template-drift.sh`** (PreToolUse Write|Edit on adapter template JSONs) — **transitional** hook that warns against hand-editing generated templates. Delete when registry is fully established.

All four registered in the manifest as `category: meta, phase: G`.

#### G.4 — Documentation

- [x] AGENTS.md adds "Hook Visibility — See What Fires" section explaining the new commands.
- [x] AGENTS.md Navigation Cheatsheet: "Add a new hook" now points at `registry.yaml`.
- [x] AGENTS.md "Derived artifacts" table includes both adapter template files.

**Phase G totals: 4 new hooks (3 permanent + 1 transitional), 1 new YAML manifest, 1 new Python renderer module, 1 new Makefile target, 2 new CLI commands (hooks-log, hooks-list), new cos_log_hook helper in cos-env.sh. Cumulative hook count: 35 (was 31 counted; 33 in Phase F totals included some un-counted utility scripts).**

### Done — Phase H (identity-aware logging + shared fundamentals skills) — v0.2.4

Phase H makes the logging layer identity-aware (so concurrent agents never mix their traces) and extracts the shared-patterns-across-stacks into two canonical "fundamentals" skills, re-plumbed through `depends_on` frontmatter. Also documents every hook that already existed — the ship-before-docs debt Phase G left behind.

#### H.1 — Identity-aware hook logging

- [x] `cos_log_hook` in [core/hooks/cos-env.sh](../core/hooks/cos-env.sh) now emits `agent=X session=Y task=Z` on every line. Detection priority: explicit `COS_AGENT` env → runtime env heuristics (`CLAUDECODE`, `CODEX_*`) → `.coding-os/.agent` file written by adapter `install.sh` → `unknown`.
- [x] Two new helpers — `cos_current_session` and `cos_current_task` — are pure reads over `$COS_SESSION_FILE` and `$COS_STATE_DIR/.task-current`. Cheap enough to call on every hook invocation.
- [x] Adapter install scripts ([claude](../adapters/claude/install.sh), [codex](../adapters/codex/install.sh)) persist agent identity to `.coding-os/.agent` on install — belt-and-suspenders with env heuristics.
- [x] `cos hooks-log` gains `--agent`, `--session`, `--task`, `--hook` filters (AND semantics, fixed-string match). Works both with and without `--follow`.

Result: `cos hooks-log --agent claude --session ses-20260418-...` gives a clean trace for one chat across one runtime, even when multiple agents run concurrently against the same project. Solves the "whose activity is this?" problem that the old format forced `grep` gymnastics on.

#### H.2 — Shared fundamentals skills (backend + frontend)

- [x] New [core/skills/backend-fundamentals/SKILL.md](../core/skills/backend-fundamentals/SKILL.md) — 16 sections: scale mindset, service/selector split, response envelope, idempotency, N+1, indexes, pagination, transactions, migrations, auth, logging, external calls, async jobs, audits, validation, rate limiting + PR checklist.
- [x] New [core/skills/frontend-fundamentals/SKILL.md](../core/skills/frontend-fundamentals/SKILL.md) — 14 sections: three-state async UI, server vs client components, hydration safety, error boundaries, a11y, performance, state management, forms, SEO, i18n, localStorage, mobile, testing + PR checklist.
- [x] Stack skills (`python-django`, `python-fastapi`, `go-patterns`, `go-fiber`, `nextjs-react`) declare `depends_on: [clean-code, <fundamentals>]` in frontmatter. Agent loads fundamentals transitively — one concern source, DRY across stacks.
- [x] [docs/engineering/skill-architecture.md](./engineering/skill-architecture.md) explains the base + specialization layering and the "shared vs specific" decision rule.

Result: adding a 6th backend stack (Rails, NestJS, Spring, …) now costs ONLY the stack-specific layer. Cross-cutting patterns (idempotency, envelopes, migrations) are updated once in `backend-fundamentals` and propagate to every stack via the `depends_on` graph. Matches Claude Certified Architect Foundations TS 3.2 skill composition pattern.

#### H.3 — Documentation backfill (what already existed but wasn't documented)

- [x] New [docs/engineering/hooks-reference.md](./engineering/hooks-reference.md) — catalog of all 35 hooks, organized by category (safety / enforcement / observability / reminder / meta), with fire-on columns and effect class (BLOCK / WARN / SILENT).
- [x] New [docs/engineering/template-enforcement.md](./engineering/template-enforcement.md) — documents the already-existing `enforce-template.sh` hook: which 4 markdown classes it blocks, the design principle (SSOT-only, not all markdown), escape hatch, how to extend.
- [x] New [docs/engineering/skill-architecture.md](./engineering/skill-architecture.md) — documents the new skill composition model.
- [x] New [docs/engineering/templates-location-analysis.md](./engineering/templates-location-analysis.md) — personas + scenarios analysis of "templates as files" vs "templates in CLI" vs "hybrid". Recommendation: stay with files (status quo), revisit at 10+ template classes.
- [x] [core/hooks/doc-sync-reminder.sh](../core/hooks/doc-sync-reminder.sh) now points at the new engineering docs when code changes in related areas (completing the loop: code edit → reminder → doc).

Result: the hook regime shipped in Phase E–G is now fully documented. No more "that hook exists but I didn't know" surprises.

**Phase H totals: 2 new fundamentals skills, 5 stack skills updated with `depends_on`, 4 new engineering docs, `cos_log_hook` identity-enriched, 4 CLI filter flags, 2 helpers in cos-env.sh.**

### Known Issues (deferred to v0.3.0)

- [ ] Cursor adapter not built (stub only)
- [ ] No `migrate-from-nako` command yet
- [ ] Full wheel packaging (bundled data files) — only editable install works for now
- [ ] Shell completion (click integration)

## Planned (v0.3.0)

### Agent Parity

- [ ] Auto-detect agent from project

### CLI Improvements

- [ ] `cos setup --mode describe` (LLM-backed PRD draft)
- [ ] Shell completion (click integration)

### Templates — Phase 1 targets (user priorities as of 2026-04-18)

- [ ] **Go stack hardening** — `templates/go/` exists; audit against `core/skills/backend-fundamentals` for gaps; add RFC-9457 problem-detail error envelope example
- [ ] **Go-Fiber stack hardening** — same audit for `templates/go-fiber/`; add graceful shutdown + middleware composition examples
- [ ] **Postgres cross-cutting skill** — new `core/skills/postgres-fundamentals/SKILL.md` covering RLS, migration discipline, `EXPLAIN ANALYZE` workflow, connection pooling, logical replication caveats. Referenced from `backend-fundamentals` §5–§8.
- [ ] **React Native stack** — new `templates/react-native/` with scaffold + `templates/react-native/skills/react-native/SKILL.md`. `depends_on: [clean-code, frontend-fundamentals]`. Covers New Architecture (RN 0.76+), navigation (expo-router vs react-navigation), reanimated patterns, SafeAreaView, async storage, OTA updates.
- [ ] **TypeScript shared skill** — new `core/skills/typescript-fundamentals/SKILL.md` covering `strict` mode, discriminated unions, `never` exhaustion checks, `satisfies`, branded types, and the TypeScript 5.x+ type-flow improvements. Used by `nextjs-react` and the future `react-native` skill via `depends_on`.
- [ ] **Supabase BaaS overlay** — new orthogonal dimension `templates/baas/supabase/`. RLS patterns, edge-function skill, migration convention, `_shared/provider-safe.ts` pattern, dual-currency ledger pattern (from ZibalVPN production lessons).
- [ ] **Docker infra overlay** — new orthogonal dimension `templates/infra/docker/`. Multi-stage Dockerfile per stack, `docker-compose.yml` + `.dockerignore`, `check-docker-build.sh` hook.
- [ ] **Rails template** (deferred from earlier plan — lower priority than above)
- [ ] **Generic "any backend" template** — minimal scaffold referencing only `backend-fundamentals`, for stacks without a dedicated skill.

### Orthogonal dimensions (new taxonomy — planned v0.3.0)

Introduces a three-axis composition model beyond the current single "stack" axis:

```
templates/stacks/    — one required:    django · nextjs · fastapi · go · go-fiber · react-native
templates/baas/      — optional many:   supabase · firebase · appwrite
templates/infra/     — optional many:   docker · k8s · github-actions · terraform
```

CLI shape: `cos init --stack go-fiber --baas supabase --infra docker,github-actions`. Currently `templates/{django,nextjs,go,go-fiber,fastapi}/` live at the top level; migration moves them into `templates/stacks/` and updates `cli/main.py` + `scaffold_manifest.json` derivation. Golden snapshots regen in the same commit.

## Deferred / Dropped

- **Cursor adapter** — removed in Phase F. The `.cursorrules` file format lacks the hook lifecycle events we rely on; adding it as a third adapter was over-scope for a feature nobody actually requested. Can be revived as a community contribution if demand appears.
- **`cos migrate-from-nako`** — dropped. NakoDigital was the pre-coding-os reference project whose workflow we generalized; a one-shot migration tool was never used.
- **Full wheel packaging** — deferred. Editable install (`uv tool install --editable`) covers every real-world usage today. Wheel packaging needs bundling 32 shell hooks + scaffold trees + template directories with careful path-resolution for installed vs editable mode. Re-visit when the first external user hits it.

### Learning Enhancements

- [ ] Cross-project pattern sharing (opt-in)
- [ ] Pattern confidence visualization
- [ ] Automatic rule generation from high-confidence patterns
- [ ] HNSW index for >50K vector workloads (Phase B currently brute-force)
