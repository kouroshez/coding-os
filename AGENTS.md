# AGENTS — Coding OS Development Protocol (META PROJECT)

Purpose: Root entry point for agents working **ON** the coding-os project itself — not FOR a project that merely consumes coding-os.
Read when: Starting any task or re-grounding after context loss.

## 🧬 Nature — Meta-Project (READ FIRST, 30s)

**This repo IS the mother.** coding-os is a meta-project: its output is projects shaped like itself. A consumer project created by `cos init` inherits the same skeleton you are reading now — same `.coding-os/`, same hooks, same thinking-os MCP, same `AGENTS.md` shape — only the `stack` (django, nextjs, go-fiber, ...) and `agent` (claude, codex) differ.

**Three concentric layers:**

- **`core/`** — the agent-agnostic, stack-agnostic kernel. Shared by every project. Hooks, MCP server, rules, skills, commands, scripts. *(Biological analogy: the DNA.)*
- **`adapters/<agent>/`** — per-agent translation: how the kernel surfaces as `.claude/` or `.codex/`. *(mRNA.)*
- **`templates/<stack>/`** — per-stack overlay: skills and scaffold docs that only make sense for one language/framework. *(Phenotype.)*

`cos init` composes DNA + mRNA + phenotype → a new project. **This repo is ALSO an instance of the phenotype it produces** — it dogfoods itself (P5). The `.claude/` and `.codex/` in this root are the same symlink-sets a fresh `cos init` produces.

**Golden rule of meta-editing:**
- Every edit in `core/**` propagates to every consumer project on `cos update`. Edit deliberately.
- Every edit in `adapters/<X>/` only affects users of agent X.
- Every edit in `templates/<Y>/` only affects users of stack Y.
- Every edit in `cli/**` changes the factory itself — requires `uv tool install --editable .` to take effect.

> **Local quirk (this repo only):** `CLAUDE.md` at the root is a symlink to `AGENTS.md`, for backward-compatibility with older tooling and bookmarks. Consumer projects produced by `cos init` do **not** have a `CLAUDE.md` — they have only `AGENTS.md`, which both Claude Code and Codex read natively. Do not rely on `CLAUDE.md` in generated projects.

## Hook Visibility — See What Fires

Hooks are installed by the adapter install scripts. Seeing them *actually fire* during a session is answered by three tools:

| Question | Command |
|---|---|
| What hooks ran in this session? | `cos hooks-log` (tail `.coding-os/.hooks.log`) |
| Follow hook activity live | `cos hooks-log --follow` |
| What hooks exist, filtered by agent? | `cos hooks-list --agent codex` (or `claude`) |
| Same, filtered by category | `cos hooks-list --category safety` |
| Same, filtered by phase | `cos hooks-list --phase G` |

Every hook sources `core/hooks/cos-env.sh` and calls `cos_log_hook <name> <action>` on entry / decision. If `cos hooks-log` shows zero entries for a hook you expected to fire, the hook is not being delivered by the agent runtime — typically because `.claude/settings.json` or `.codex/hooks.json` changed mid-session and the agent did not reload.

**SSOT for hook registration:** [core/hooks/registry.yaml](core/hooks/registry.yaml). This file is declarative — every hook is declared once with its events, matchers, category, and phase. The two adapter template files (`adapters/claude/settings.template.json`, `adapters/codex/hooks.template.json`) are **generated** from this manifest via `make regen-adapter-templates`. Never hand-edit them — the `warn-template-drift.sh` hook catches that.

## Mental Model

```
                 ┌───────────────────────────────────────┐
                 │  core/   (DNA — agent+stack agnostic) │
                 │  ├── hooks/         (45 .sh scripts)  │
                 │  ├── thinking-os/   (MCP, 29 tools)   │
                 │  ├── graph-os/      (Phase I v12 KG)  │
                 │  ├── board-os/      (Phase L Scrumban)│
                 │  ├── rules/  skills/  scripts/        │
                 │  └── commands/  docs/                 │
                 └───────────────┬───────────────────────┘
                                 │ symlinked / sourced by
                ┌────────────────┼────────────────┐
                ▼                ▼                ▼
      ┌──────────────┐  ┌──────────────┐   ┌──────────────┐
      │ adapters/    │  │ adapters/    │   │ (future)     │
      │   claude/    │  │   codex/     │   │   cursor/    │
      │  (mRNA)      │  │  (mRNA)      │   │              │
      └──────┬───────┘  └──────┬───────┘   └──────────────┘
             │                 │
             └────────┬────────┘
                      │ composed with chosen stacks
                      ▼
             ┌────────────────────┐
             │ templates/         │  → phenotype (django / nextjs / ...)
             │   _base/           │  → skeleton shared by all stacks
             └─────────┬──────────┘
                       │
        `cos init`  │  `cos add-adapter`  │  `cos add-stack`
                       ▼
          ┌───────────────────────────────────────┐
          │ Consumer project (or THIS repo)       │
          │   AGENTS.md  .coding-os/  .mcp.json   │
          │   .claude/ and/or .codex/             │
          └───────────────────────────────────────┘
```

## Modularity Map — Blast Radius of Edits

| You edit | Propagates to | Rebuild command |
|---|---|---|
| `core/hooks/*.sh` | **ALL** consumer projects + this repo (symlinks resolve live) | none — live |
| `core/thinking-os/**` | ALL projects pointing to this MCP server | restart MCP client |
| `core/rules/*.md` | ALL projects (symlinked into both `.claude/rules/` and `.codex/rules/`) | `cos update` in consumer |
| `core/skills/**` | ALL projects | `cos update` in consumer |
| `adapters/claude/**` | Only projects with claude adapter | `cos update` or re-run `install.sh` |
| `adapters/codex/**` | Only projects with codex adapter | `cos update` or re-run `install.sh` |
| `templates/<stack>/**` | Only projects using that stack | `cos update` + `make manifest-regen` |
| `templates/_base/**` | ALL projects (base skeleton) | `cos update` + `make manifest-regen` |
| `cli/**` | ALL future `cos` invocations (the factory itself) | `uv tool install --editable .` |

**Derived artifacts — never hand-edit; regenerated from sources above:**
- `core/rules/dimension-registry.md` ← `templates/*/stack.yaml` (via `make regen-rules`)
- `core/rules/skill-enforcement.md` ← same source, same command
- `core/scaffold_manifest.json` ← `templates/**/scaffold/**` (via `make manifest-regen`)
- `adapters/claude/settings.template.json` ← `core/hooks/registry.yaml` (via `make regen-adapter-templates`)
- `adapters/codex/hooks.template.json` ← `core/hooks/registry.yaml` (via `make regen-adapter-templates`)
- `tests/golden/**` ← end-to-end `cos init` outputs (via `capture_golden.py`)

The `regen-reminder.sh` and `warn-template-drift.sh` hooks warn on hand-edits to any of these.

## Explicit Core — MCP + thinking-os + graph-os + board-os

The **cognitive layers** of coding-os are three peer subsystems under `core/`, all registered on the same MCP server at `core/thinking-os/server.py`:

- **thinking-os** (memory + learning + metrics) — the hippocampus. "Have I seen this before?"
- **graph-os** (Phase I) — the corpus callosum. "What is connected to what?"
- **board-os** (Phase L) — the prefrontal cortex / planner. "What am I going to do next?"

Hooks enforce rules; templates standardize layout; **the three OS subsystems are where cognition, structure, and planning live.**

- **Server entry**: [core/thinking-os/server.py](core/thinking-os/server.py) — FastMCP, registers **29** `cos_*` tools across 8 categories (Health · Memory · Metrics · Learning · Routing · Graph · Docs RAG · Tasks + Board).
- **DB**: SQLite with WAL + FTS5 + sentence-transformer embeddings. Schema v1–v13 (append-only migrations, Rule 10). Path: `$COS_DB_PATH` (default `.coding-os/thinking-os.db`). **Kùzu** (`.coding-os/graph-os.kuzu`) for Phase I graph-native workloads when `graph.backend: kuzu`.
- **Client wiring**: `.mcp.json` at the project root. Adapter install scripts populate this file automatically.
- **Four-layer retrieval** (see "Four-Layer Retrieval" below): Agent Memory · Doc Knowledge Base · Task Registry · Knowledge Graph.
- **Liveness matters**: if MCP is down, the session is cognitively blind — hooks fire but nothing remembers. `warn-mcp-down.sh` (SessionStart) and `cos doctor` check C15 exist specifically to surface this.

## Navigation Cheatsheet — "I want to X, go to Y"

| I want to... | Go to |
|---|---|
| Add a new hook | `core/hooks/<new>.sh` + add entry to `core/hooks/registry.yaml` + `make regen-adapter-templates` + `make dogfood-full` |
| Add a new MCP tool | `core/thinking-os/tools/<category>.py` (or `core/graph_os/tools/` / `core/board_os/mcp_tools.py`) + register in `core/thinking-os/server.py` |
| Create a task | `cos_task_create(title, swimlane, kind, priority)` MCP or `cos task-create --swimlane X --kind Y --title Z` CLI |
| Move a task across the board | `cos_task_move(task_id, to='in_progress')` or `cos task-start TASK-NNN`, `cos task-done TASK-NNN` |
| View the board | `cos board` (ASCII) · `cos board --web` (http://127.0.0.1:9000) · `cos daily` · `cos retro` |
| Add a new agent (e.g. cursor) | `adapters/<id>/{adapter.yaml, install.sh, *.template.*}` + tests in `tests/test_adapters.py` |
| Add a new stack (e.g. rails) | `templates/<id>/{stack.yaml, scaffold/, skills/}` + golden in `tests/golden/` |
| Add a new rule | `core/rules/<name>.md` — auto-symlinked into both `.claude/rules/` and `.codex/rules/` by the install scripts |
| Change CLI behavior | `cli/*.py` — data-driven from `stack.yaml` / `adapter.yaml` (Rule 12: no hardcoded literals) |
| Add a DB migration | `core/thinking-os/db.py` — append-only, new `_migrate_vN()` function (Rule 10) |
| Verify current state | `make verify` · `make cos-health` · `cos doctor` |
| Understand any AGENTS.md fragment | `templates/_base/base.yaml::agents_md_sections` maps section IDs → `fragments/*.tmpl` |
| Trace what an edit affects | See the "Modularity Map" table above |

## Identity

coding-os: Agent-agnostic cognitive operating system for AI coding agents. Teaches agents **how to think** (thinking-os) and **how to code** (workflow, hooks, skills, rules). Stack: Python + Shell + Markdown. Architecture: Hexagonal (core → adapters → templates).

## Principles

P1. SSOT-first — no parallel truths.
P2. Agent-agnostic — never hardcode `.claude/` or `.codex/` in core. Use `$COS_STATE_DIR`.
P3. Minimal-context — 3-10 files max per task.
P4. Diff-first — preserve unrelated content.
P5. Dogfood — coding-os uses itself for development.
P6. Log-everything via make commands.
P7. No-guessing — log unknowns to docs/questions.md.

## Architecture

```
coding-os/
├── core/                 # Agent-agnostic (THE PORT)
│   ├── thinking-os/      # MCP server: 29 cos_* tools, SQLite DB v13, self-learning
│   │   ├── server.py     # FastMCP entry, registers all cos_* tools
│   │   ├── db.py         # Schema v1-v13 migrations, WAL mode, FTS5
│   │   ├── embeddings.py # Phase B: sentence-transformers + numpy cosine (`rag` extra)
│   │   ├── doc_indexer.py# Phase B: heading-aware markdown chunker → document_chunks
│   │   ├── task_parser.py# Phase C: legacy 12-section parser (kept as fallback)
│   │   ├── task_sync.py  # Phase C: mtime-incremental sync → tasks table
│   │   └── tools/        # memory, metrics, learning, routing, docs, tasks
│   ├── graph_os/         # Phase I: knowledge graph (Kùzu + SQLite backends)
│   │   ├── backend.py    # Protocol for kuzu vs sqlite graph backends
│   │   ├── extractors/   # (Phase I.2+) md_links, code_python, code_ts, contracts
│   │   └── backends/     # kuzu_backend.py + sqlite_backend.py
│   ├── board_os/         # Phase L: Scrumban task system (cos-board)
│   │   ├── config.py     # ScrumbanConfig + 8-value kind/status enums
│   │   ├── parser.py     # Lean frontmatter parser + legacy fallback
│   │   ├── sync.py       # mtime-incremental task→DB sync, status-history
│   │   ├── workflow.py   # 8-state machine + WIP + cycle detection (R-L-29)
│   │   ├── mcp_tools.py  # 8 cos_task_* tools + cos_work_log_append
│   │   ├── migration.py  # Two-phase atomic legacy→lean migration (L.7)
│   │   └── viewer/       # aiohttp + Sortable.js web board
│   ├── hooks/            # 45 shell scripts, parameterized via cos-env.sh
│   ├── scripts/          # task/log/ref/docs management scripts
│   ├── rules/            # thinking-os.md (Complexity Gate), memory.md
│   ├── skills/           # thinking-os, clean-code, codebase-explorer, worktree, task-driver
│   ├── commands/         # task.md, review.md, diagnose.md
│   └── docs/             # thinking-os-final-edition (1439L), agent-workflow, task-lifecycle
├── adapters/             # Per-agent translation (THE ADAPTERS)
│   ├── claude/           # settings.template.json, install.sh
│   └── codex/            # hooks.template.json, install.sh
├── templates/            # Per-stack content (THE TEMPLATES)
│   ├── _base/            # AGENTS.template.md, Makefile.base, scaffold/, rag-config.yaml, scrumban-config.yaml
│   ├── django/           # python-django skill + scaffold/docs overlay
│   ├── nextjs/           # nextjs-react + frontend-design + scaffold/docs overlay
│   ├── fastapi/ go/ go-fiber/  # per-stack scrumban-config.yaml swimlanes
│   └── _base/fragments/  # AGENTS.md composable sections (incl. task-authoring L.9)
├── cli/main.py           # Python+click: init, add-adapter, health, eject
├── cli/board_commands.py # Phase L.6: 16 board-os CLI commands
├── scripts/              # verify_phase_c_e2e.py, populate_board_from_phases.py, ...
└── docs/                 # architecture, getting-started, roadmap, phase-*-plan
```

## Request Routing

**Gate 1 — Complexity Gate** (always): Q1 Cynefin → Q2 Dimension count. Record:
```bash
bash core/hooks/write-state.sh .coding-os/.thinking-os-gate "COMPLICATED 3"
```

**Gate 2 — Request Type**: A (Question) → answer directly. B (Task) → Core Loop. C (Ad-hoc trivial) → inline fix.

## Core Loop

**Classify → Orient → Plan → Execute → Verify & Close**

### Classify (dry — zero file reads)
1. Complexity Gate — record classification
2. Domain route: Python (`core/thinking-os/`, `cli/`) → python rules. Shell (`core/hooks/`, `core/scripts/`) → shell rules. Markdown → doc rules.
3. Read List — identify files to read

### Orient (targeted reads)
1. Read ONLY files from Read List
2. Memory check: `cos_search` for past patterns
3. Repo search: grep/glob existing code

### Plan (analysis)
1. Per dimension: current → target → gap → risk
2. Action plan with ordered steps

### Execute (implement)
1. Smallest correct change
2. After code changes: run verification

### Verify & Close
1. Run: `make verify`
2. Log: `make task-done TASK=N TYPE=feat MSG="..." WHAT="..." FILES="..."`

## Verification Matrix

| Changed files | Required checks | Commands |
|---|---|---|
| `core/thinking-os/*.py` | Pytest + MCP self-test | `uv run --extra rag pytest core/thinking-os/tests/ -q` and `python core/thinking-os/server.py --test` |
| `core/thinking-os/db.py` | Migration tests | `uv run --extra rag pytest core/thinking-os/tests/test_db.py -q` |
| `core/thinking-os/doc_indexer.py` or `task_sync.py` | E2E verification | `python scripts/verify_phase_c_e2e.py` |
| `core/graph_os/**` | graph-os parity + extractor tests | `uv run --extra graph-os pytest core/graph_os/tests/ -q` |
| `core/board_os/**` | board-os tests (parser, sync, workflow, MCP, viewer) | `uv run --extra rag --with aiohttp --with pytest-asyncio pytest core/board_os/tests/ -q` |
| `core/hooks/*.sh` | Shell syntax check | `make verify-hooks` |
| `core/scripts/*.sh` | Shell syntax check | `make verify-hooks` |
| `adapters/**` | Adapter install test | `uv run pytest tests/test_adapters.py -q` |
| `cli/*.py` | CLI integration tests | `uv run pytest tests/test_cli.py -q` |
| `templates/_base/scaffold/**` | Template scaffold tests | `uv run pytest tests/test_template_scaffold.py -q` |
| `templates/_base/task-detail.template.md` | Lean template parity | `uv run pytest core/board_os/tests/test_template_parity.py -q` |
| `.coding-os/scrumban-config.yaml` | Config schema + per-stack defaults | `uv run pytest core/board_os/tests/test_config.py core/board_os/tests/test_per_stack_configs.py -q` |
| `docs/**/*.md` | Docs lint + staleness check | `make docs-lint` (includes docs-staleness-check.sh) |

## Tool Routing

**Legacy task flow (still supported for backward-compat; prefer Scrumban below):**
- `make session-init`, `task-next`, `task-start TASK=N`, `task-done TASK=N TYPE=t MSG="m" WHAT="w" FILES="f"`, `task-block TASK=N REASON="r"`, `task-create NUM=N TITLE="t"`.

**Phase L Scrumban flow (board-os — preferred):**
- **CLI:** `cos board` (ASCII) / `cos board --web` (http://127.0.0.1:9000) · `cos task-create --title ... --swimlane ... --kind ...` · `cos task-start TASK-NNN` · `cos task-move TASK-NNN --to testing` · `cos task-done TASK-NNN` · `cos task-block TASK-NNN --reason ...` · `cos task-cancel TASK-NNN` · `cos task-pick` · `cos daily` · `cos retro` · `cos wip` · `cos task-show TASK-NNN` · `cos task-log TASK-NNN [--full]` · `cos task-history TASK-NNN` · `cos task-validate` · `cos board-config --init --stack <stack>`.
- **MCP:** `cos_task_create`, `cos_task_board`, `cos_task_move`, `cos_task_pick`, `cos_task_daily`, `cos_task_retro`, `cos_task_wip_check`, `cos_work_log_append` (Codex MUST call the last one explicitly — no PostToolUse hook).

**Log**: `log-latest [N]`, `log-write TYPE=t MSG="m" WHAT="w" FILES="f"`, `log-search QUERY="q"`.

**Verify**: `verify`, `verify-hooks`, `test-mcp`, `test-install`, `cos-health`.

## Critical Rules

0. **Docs-first principle (highest priority)** — Docs are the single source of truth. Every code Write/Edit must trace to a doc path recorded in `$COS_AGENT_DIR/.doc-anchor` (populated by `task-start.sh` from the task file's "Source of Truth" / "Read First" sections). `enforce-doc-anchor.sh` BLOCKS code writes without an anchor. If the task has no doc to cite, either (a) mark CLEAR 1 gate for trivial fixes, (b) use an `exploratory-*` task name for spikes, or (c) stop and ask the user what doc should exist first — never invent implementation from scratch.

1. **Never hardcode `.claude/`** in `core/` — use `$COS_STATE_DIR` (shared root: DB, log, `.agent` marker), `$COS_AGENT_DIR` (agent-private: session-id + all session-scoped markers — `.coding-os/<agent>/`), or `$COS_DB_PATH` env vars. Full design: [docs/engineering/state-files.md](docs/engineering/state-files.md).
2. **MCP tool names use `cos_*` prefix** — **29** tools total across 8 categories:
   - Health (1): `cos_health`
   - Memory (4): `cos_search`, `cos_timeline`, `cos_details`, `cos_promote`
   - Metrics (3): `cos_metric_record`, `cos_metric_query`, `cos_metric_trend`
   - Learning (5): `cos_learn_extract`, `cos_learn_suggest`, `cos_learn_validate`, `cos_learn_feedback`, `cos_learn_narrative`
   - Routing (2): `cos_route_model`, `cos_route_skill`
   - Graph (1): `cos_graph`
   - Docs RAG (1): `cos_doc_search` — Phase B
   - Tasks (4): `cos_task_search`, `cos_task_dependencies`, `cos_task_dependents`, `cos_task_by_filter` — Phase C
   - Board (8): `cos_task_create`, `cos_task_board`, `cos_task_move`, `cos_task_pick`, `cos_task_daily`, `cos_task_retro`, `cos_task_wip_check`, `cos_work_log_append` — Phase L
   - Retrieval feedback (1): `cos_retrieval_cite` — Phase G.8
3. **Hooks source `cos-env.sh`** — `source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true`
4. **Scripts search config chain** — `$COS_STATE_DIR/domain-config.json` → `infrastructure/scripts/domain-config.json`
5. **State lives in `$COS_AGENT_DIR`, NOT `.claude/`** — per-session markers (`session-id`, `.task-current`, `.thinking-os-gate`, `.zoom-checkpoint`, `.doc-anchor`, `.memory-check`, `.active-skill`) live in `.coding-os/<agent>/` so two agents on the same repo never share ephemeral state. Shared artifacts (DB, `.hooks.log`, `.agent` marker, `installed-manifest.json`) stay at `.coding-os/`. Session-id is agent-prefixed: `ses-claude-YYYYMMDD-...` / `ses-codex-YYYYMMDD-...`. The pre-2026-04 `.claude/.session-id` fallback was removed as dead code.
6. **Path resolution** — always call `.resolve()` before `relative_to()` on macOS (`/tmp` ↔ `/private/tmp` symlink). Regression-tested in `test_doc_indexer.py::TestPathResolutionRegression` and `test_task_sync.py::TestSyncPathResolutionRegression`.
7. **Fire-and-forget with explicit exception handling** — use `except Exception as exc: logger.debug(...)` inside a dedicated `_embed_*_safe()` helper instead of bare `except: pass`. The `block-bad-patterns.sh` hook rejects the latter.
8. **Governance edits require explicit task name** — edits to `CLAUDE.md`, `AGENTS.md`, `.coding-os/`, `core/rules/`, or `core/hooks/` require the active task marker to include `docs-update`, `governance`, etc. Set via `bash core/hooks/write-state.sh .coding-os/.task-current "docs-update-<slug>"`.
9. **Always use Python for multi-step verification scripts** — bash heredoc inside `$(...)` with `uv run` hangs. Write to a Python file and invoke via `subprocess.run(..., timeout=N)`. See `scripts/verify_phase_c_e2e.py`.
10. **Schema migrations are append-only** — new tables → migration vN+1, never edit past migrations. Add `has_<table>_table(conn)` helper and include the table in `_TABLES` list. **Enforced by `block-migration-conflict.sh`** (rejects duplicate version in `db.py`).

11. **Regenerate derived artifacts when source files change** — `templates/*/stack.yaml` → `make regen-rules` + `make manifest-regen`; `adapters/*/adapter.yaml` → `make manifest-regen`; any `scaffold/**` → `make manifest-regen` + `capture_golden`. **Reminder hook: `regen-reminder.sh`** prints the exact commands when you touch a source-of-truth file, and warns if you hand-edit a generated one (`core/rules/dimension-registry.md`, `core/rules/skill-enforcement.md`, `core/scaffold_manifest.json`, `tests/golden/**`).

12. **No hardcoded stack/adapter literals in `cli/*.py`** — the CLI layer is data-driven from `stack.yaml` / `adapter.yaml`. `block-hardcoded-literals.sh` (edit-time) + `tests/test_no_hardcoded_stacks.py` (test-time) catch `"django"` / `"claude"` / `"python-django"` as quoted literals in `cli/*.py`. Move new metadata to YAML fields, read via the registry.

13. **Function header convention for new Python / TypeScript** (applies to new modules and new public functions under `core/thinking-os/**` and `cli/**`; legacy code is not retrofitted — P4 Diff-first). Every new top-level function / class method exposed as MCP tool, CLI command, parser, or indexer MUST start with a structured docstring header:

    ```python
    def cos_task_search(...) -> list[TaskRow]:
        """
        PURPOSE:      What this function does and why it exists.
        INPUT:        {typed shape — link to dataclass / TypedDict if one exists}
        OUTPUT:       {return shape, including error envelope on MCP tools}
        DEPENDENCIES: DB tables, MCP tools, sibling modules touched.
        NOTES:        Edge cases, idempotency, non-obvious invariants.
        """
    ```

    Pure helpers under 5 lines are exempt. Rationale: the MCP server is the cognitive heart of the repo (C15) — a future agent reading `server.py` / `tools/*.py` gets the *why* without hunting through call sites. Convention only for now (no hook enforcement); revisit if drift appears.

14. **MCP tool response envelope** — every `cos_*` tool in [core/thinking-os/server.py](core/thinking-os/server.py) MUST return via `ok(data)` or `fail(category, message)` from [core/thinking-os/tools/_shared.py](core/thinking-os/tools/_shared.py). The envelope is `{ok: true, data: T}` on success or `{ok: false, error: {category, retryable, message}}` on failure. Categories: `transient | validation | permission | not_found | unavailable | internal`. Every tool must also be wrapped in `@safe_tool` (inside `@mcp.tool(...)`) so unhandled exceptions become `fail("internal", ...)` instead of raw tracebacks. Consumers (agents, tests) drill through `envelope["data"]` rather than the top level. Full contract: [docs/engineering/mcp-error-envelope.md](docs/engineering/mcp-error-envelope.md). Rationale: TS 2.2 of Claude Certified Architect Foundations — agents need `retryable` to recover instead of looping uselessly.

15. **Tasks are pointers, not specs (Phase L, board-os)** — A task file under `docs/tasks/TASK-NNN-slug.md` MUST NOT inline content already present in `docs/**`, `core/rules/**`, `AGENTS.md`, or `CLAUDE.md`. The `Read First` section lists *paths*; the body describes *delta* only (Outcome + Acceptance G/W/T + Work Log). Duplicated content is a bug — fix by linking, or by writing the referenced doc first (Formula 4) then linking. **Enforced by `lint-task.sh` PostToolUse hook** (warns >1.5k tokens, blocks >3k). The four categorization axes are orthogonal: `swimlane` (domain, config-enum), `kind` (type, 8-value closed enum drives card colour), `epic` (initiative, optional free string), `labels` (free tags; MUST NOT contain kind values). Full rationale: [docs/phase-l-scrumban-task-system-plan.md §15](docs/phase-l-scrumban-task-system-plan.md).

## Key Files

| What | Where |
|------|-------|
| MCP server entry | `core/thinking-os/server.py` |
| DB module + migrations v1-v13 | `core/thinking-os/db.py` |
| Phase B embeddings engine | `core/thinking-os/embeddings.py` |
| Phase B doc indexer | `core/thinking-os/doc_indexer.py` |
| Phase C task parser (legacy) | `core/thinking-os/task_parser.py` |
| Phase C task sync (legacy) | `core/thinking-os/task_sync.py` |
| MCP tools (7 modules) | `core/thinking-os/tools/{memory,metrics,learning,routing,docs,tasks}.py` |
| Phase I graph-os protocol + backends | `core/graph_os/backend.py`, `core/graph_os/backends/{kuzu,sqlite}_backend.py` |
| **Phase L board-os — module root** | `core/board_os/` |
| Phase L scrumban config model | `core/board_os/config.py` (KIND_ENUM, STATUS_ENUM, PRIORITY_ENUM) |
| Phase L lean task parser | `core/board_os/parser.py` (frontmatter + legacy fallback) |
| Phase L workflow engine | `core/board_os/workflow.py` (state machine + WIP + cycle detect) |
| Phase L MCP surface | `core/board_os/mcp_tools.py` (8 `cos_task_*` tools) |
| Phase L web viewer | `core/board_os/viewer/server.py` (aiohttp + Sortable.js) |
| Phase L CLI surface | `cli/board_commands.py` (16 commands) |
| Phase L task template (lean) | `templates/_base/task-detail.template.md` |
| Phase L scrumban config (meta) | `.coding-os/scrumban-config.yaml` |
| Phase L scrumban config (per-stack) | `templates/<stack>/scaffold/.coding-os/scrumban-config.yaml` |
| Phase L AGENTS.md fragment | `templates/_base/fragments/task-authoring.md.tmpl` (order 135) |
| Phase L task-driver skill | `core/skills/task-driver/SKILL.md` |
| Hook config loader | `core/hooks/cos-env.sh` |
| Protected files hook (with task-name escape hatch) | `core/hooks/block-protected-files.sh` |
| CLI entry | `cli/main.py` |
| Claude adapter | `adapters/claude/install.sh` |
| Codex adapter | `adapters/codex/install.sh` |
| Base Makefile (incl. docs-index, task-sync, cos-reindex) | `templates/_base/Makefile.base` |
| Project template | `templates/_base/AGENTS.template.md` |
| RAG scaffold config | `templates/_base/scaffold/.coding-os/rag-config.yaml` |
| E2E verification | `scripts/verify_phase_c_e2e.py` |
| Docs staleness check | `core/scripts/docs-staleness-check.sh` |
| Phase B plan (reference) | `docs/phase-b-rag-plan.md` |
| Phase C plan (reference) | `docs/phase-c-task-store-plan.md` |
| Phase I plan (graph-os) | `docs/phase-i-knowledge-graph-plan.md` |
| Phase J plan (meta-router) | `docs/phase-j-meta-router-plan.md` |
| Phase K plan (DB abstraction) | `docs/phase-k-db-abstraction-plan.md` |
| Phase L plan (board-os / Scrumban) | `docs/phase-l-scrumban-task-system-plan.md` |

## Context Discipline

Read `docs/architecture.md` and `docs/getting-started.md` for full understanding. Note findings once, reference by path.

## Stop Conditions

Stop when: core/ changes break backward compatibility, adapter changes affect other adapters, MCP tool signature changes without migration plan.

## Four-Layer Retrieval (Phase A + B + C + I + L)

The system answers different questions at four layers. Pick the right tool:

| Layer | Question | Tools | Data |
| --- | --- | --- | --- |
| **1. Agent Memory** | "Have I solved this before?" | `cos_search`, `cos_timeline`, `cos_details`, `cos_learn_suggest` | observations, learned_patterns, outcome_history |
| **2. Document Knowledge Base** (Phase B) | "What does the spec/rule/architecture say?" | `cos_doc_search` (filter by prd/architecture/adr/api_contract/page_spec/engineering/ops/design) | document_chunks populated by `make docs-index` |
| **3. Task Registry + Scrumban** (Phase C + L) | "Which tasks are related? What depends on what? What's in progress? What's next?" | Read-only: `cos_task_search`, `cos_task_dependencies`, `cos_task_dependents`, `cos_task_by_filter`, `cos_task_board`, `cos_task_pick`, `cos_task_daily`, `cos_task_retro`, `cos_task_wip_check`. Write: `cos_task_create`, `cos_task_move`, `cos_work_log_append` | tasks table + task_status_history + MD frontmatter SSOT |
| **4. Knowledge Graph** (Phase I, partial) | "What is connected to what? What breaks if I change X?" | `cos_graph` (more `cos_graph_*` tools in I.2+) | `graph_nodes` + `graph_edges_v12` (SQLite fallback) or `.coding-os/graph-os.kuzu` |

Always-active (no retrieval, full-read): `AGENTS.md`, `CLAUDE.md`, playbooks, `core/rules/`, current task detail.

### Routing Decision (pick before you retrieve)

Before reaching for any tool, classify the query shape:

- **Identifier / exact-symbol** (function name, file path, `TASK-NNN`, snake_case, CamelCase, backticked code) → use **Grep / Glob** directly on the repo, not `cos_doc_search`. Grep wins on token cost and recall when the token actually appears. This matches how the codebase-explorer skill operates.
- **Conceptual / synonym-heavy** ("money handling", "auth flow", "commission rate calculation") → `cos_doc_search`. Semantic embedding is the only layer that finds chunks where the spec calls it "revenue split" but the agent searches "payment distribution".
- **"Have I seen this before?" / past pattern / prior solution** → `cos_search` (observations + learned_patterns, FTS5+semantic blend) and `cos_learn_suggest` (active + fading + breakthrough patterns for current context).
- **Task-graph / dependency / status** → `cos_task_*` family. Use `cos_task_search` for fuzzy title match, the `_dependencies`/`_dependents` pair for graph walks, `_by_filter` for "all open backend tasks" style queries.
- **Behavioral rule / protocol** (how to classify, how to verify, how to route) → NEVER retrieve; the rule is already in context as `core/rules/*.md`. If you think you need to retrieve it, re-read the rule file instead.

If two layers look equally plausible, prefer Memory→Docs→Tasks order — memory returns have 5-signal ranking and are tailored to past outcomes, docs and tasks are static index lookups. Each `cos_*` response carries `data.meta.layer` so you can confirm which layer answered you.

**Freshness contract (Phase H + I).** Every Write/Edit on a file matched by `.coding-os/rag-config.yaml` OR carrying a code/config suffix fires an automatic incremental re-index via the `auto-reindex-docs` PostToolUse hook ([core/hooks/auto-reindex-docs.sh](core/hooks/auto-reindex-docs.sh)). Phase I extends the hook to dispatch per-suffix to the matching graph-os extractor (`.py`/`.ts`/`.tsx`/`.sh`/`.yaml`/`.yml`/`.go`/`.md`) — so both `cos_doc_search` AND `cos_graph_*` reflect the latest state without a manual `make docs-index` / `cos graph-reindex`. Confirm with `cos hooks-log | grep auto-reindex-docs`. Codex adapter lacks Write/Edit PostToolUse matchers as of 2026-04-18, so Codex sessions rely on the opt-in background indexer (`COS_BACKGROUND_INDEX=1`) or a manual re-run.

## Graph Queries (Phase I)

The fourth retrieval layer answers "what is connected to what?" — use it whenever a change touches load-bearing code and you need the dependency picture before editing.

| Question | Tool | When |
|---|---|---|
| "What calls this function?" | `cos_graph_references(uid)` | Before renaming / removing |
| "What's around this symbol?" | `cos_graph_context(uid_or_name, depth=1)` | F5 Step 1 Pre-Implementation |
| "What breaks if I change this?" | `cos_graph_impact(uid, depth=3)` | F2 Dependency Map, F11 refactor sequencing |
| "Where is a symbol defined?" | `cos_graph_query(q)` | Lexical + graph-walk search |
| "Walk an execution path" | `cos_graph_trace(entry_uid)` | F7 Fault isolation |
| "Similar nodes?" | `cos_graph_similar(uid)` | Duplicate detection, refactor planning |
| "Shortest dependency path" | `cos_graph_path(src, dst)` | Dependency archaeology |
| "Visualise the graph" | `cos_graph_export(format='mermaid'|'json'|'dot')` or `cos graph-viz` | Diagrams in responses |
| "Diff-to-risk map" | `cos_graph_detect_changes(files=[...])` | Pre-commit self-review |

Every response carries `data.meta.layer="graph"` and `data.meta.backend` so you can confirm Kùzu vs SQLite answered. `meta.backend_fallback=true` on a response means the Kùzu path degraded to SQLite — deep walks are slower but still correct.

Full guide: [docs/engineering/graph-os-queries.md](docs/engineering/graph-os-queries.md). Skill: `graph-explorer` (auto-triggers on graph questions). Fresh re-index: `cos graph-reindex` or let the hook handle it.

## Rename Workflow (Phase I)

Never rename via grep + replace on a load-bearing function. The sequence:

1. **Call `cos_graph_rename_plan(uid, new_name)`** — returns call-sites, doc references, test references, string literals (via `check_strings=True`), comment mentions, risk tier, and a suggested order of operations.
2. **Record the marker** so the `enforce-rename-plan.sh` hook permits the subsequent Edits:
   ```bash
   bash core/hooks/write-state.sh .coding-os/claude/.rename-plan-<old_name> "reviewed"
   ```
3. **Edit in the plan's `suggested_order`:** tests first → implementation → docs → string literals last. Each Edit auto-reindexes (Phase H+I hook) so the graph reflects the rename after every step.
4. **Re-run `cos_graph_references(<new_name>)`** to confirm zero stragglers.

Hook behaviour: `enforce-rename-plan.sh` fires on `Edit` with identifier-shaped `old_string`/`new_string` pairs (both match `^[A-Za-z_][A-Za-z0-9_.]*$`, length ≤ 80). Opt into strict mode with `COS_ENFORCE_RENAME_PLAN=strict` to promote warn → block.

## Contracts Audit (Phase I — F4 + F9)

For any Formula-4 (docs) or Formula-9 (release) pass, the graph is the API surface truth:

```
cos_graph_contracts(scope="all", kinds=["http","mcp","grpc","event","websocket"])
```

Returns every detected route / tool / handler grouped by kind, with source file, line, framework, and handler uid. Use it for:
- **F4 Step 3 auto-docs:** every HTTP route + MCP tool + gRPC endpoint in one envelope → feed your doc generator.
- **F8 Layer 1 auth sweep:** cross-reference with `cos_graph_references("verify_auth")` — any route that isn't in the intersection is unauthenticated.
- **F9 release gate:** run `cos_graph_contracts` on `HEAD` and `HEAD~1`; any diff (added / removed endpoint) must be in the release notes.

Dynamic routes (template literals, reflection-based dispatch) appear with `meta.opaque_route=true` so the agent knows the surface is incomplete — not a silent gap.

## Development Status

- **v0.1.0** — Core thinking-os, hooks, rules, skills, Claude/Codex adapters, CLI ✅
- **Phase 1 (v0.1.1)** — Critical fixes: import bugs, agent-agnostic hooks ✅
- **Phase 2** — CLI/hook/adapter integration tests (72 tests) ✅
- **Phase A** — Template completion: 38 scaffold files + 38 tests ✅
- **Phase B** — RAG integration: embeddings, doc_indexer, cos_doc_search, semantic memory search (109 tests) ✅
- **Phase C** — Hybrid task store: migration v6, task_parser, task_sync, 4 `cos_task_*` tools (111 tests) ✅
- **Phase D (v0.2.0)** — CLI distribution: `cos update`, `cos setup`, `cos eject-file`, `cos server-start`, `uv tool install --editable`, 16 CLI commands ✅
- **Phase E (v0.2.1)** — Enterprise hook regime + docs-first principle: Rule 0 (doc-anchor), 6 new hooks (enforce-doc-anchor, block-migration-conflict, block-uv-heredoc, regen-reminder, block-hardcoded-literals, test-first-reminder) ✅
- **Phase F (v0.2.2)** — MCP visibility + workflow integrity: 4 new hooks (warn-mcp-down, check-capture-worked, enforce-memory-check, remind-learn-validate), doctor check C15, `make dogfood` ✅
- **Phase G** — Brain hardening: trust_tier, provenance, memory_audit, validation throttle, docs FTS, retrievals audit/feedback, retrieval quality tracker (migrations v7–v11) ✅
- **Phase H** — Auto-sync freshness: `auto-reindex-docs.sh` PostToolUse hook; `cos_doc_search` always current ✅
- **Phase I (partial)** — graph-os knowledge graph: migration v12, `core/graph_os/`, Protocol + sqlite + kuzu backends, `cos_graph` tool ✅ (I.0 shipped; I.1–I.14 on the board)
- **Phase L** — **board-os Scrumban (full)**: migration v13, `core/board_os/`, lean task template, 8 `cos_task_*` MCP tools, 6 new hooks, 16 CLI commands, web viewer at `cos board --web`, task-driver skill, AGENTS.md fragment ✅
- **Current: ~1,180 tests passing** (928 thinking-os + 146 board_os + 71 adapter + 35 literals + template scaffold + ...).

## Development Roadmap

See `docs/development-roadmap.md` for the v0.3.0 plan. Phase I.1–I.14, Phase J, and Phase K are live on the Scrumban board as icebox tasks (see `cos board` for up-to-date status).
