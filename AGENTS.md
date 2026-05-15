# AGENTS — Coding OS Development Protocol (META PROJECT)

Root entry point for agents working **ON** coding-os itself. Read first; re-read after context loss. Hard limit: keep this file under 180 lines — overflow goes to [docs/](docs/).

## Nature — Meta-Project (read first, 30s)

**This repo IS the mother.** Its output is projects shaped like itself. A consumer project from `cos init` inherits this same skeleton — same `.coding-os/`, same hooks, same MCP server, same `AGENTS.md` shape — only the **stack** (django, nextjs, go-fiber, …) and **agent** (claude, codex) differ.

Three concentric layers (DNA → mRNA → phenotype):

- **`src/core/`** — agent-agnostic, stack-agnostic kernel. Hooks, MCP server, rules, skills.
- **`src/adapters/<agent>/`** — per-agent translation: how the kernel surfaces as `.claude/` or `.codex/`.
- **`src/templates/<stack>/`** — per-stack overlay: skills + scaffold for one language/framework.

`cos init` composes DNA + mRNA + phenotype → a new project. **This repo is also an instance of what it produces** (P5 Dogfood). Root `CLAUDE.md` is a symlink to `AGENTS.md`; consumer projects only have `AGENTS.md`.

## Mental Model

```
src/core/  ──►  src/adapters/<agent>/  ──►  src/templates/<stack>/  ──►  consumer project
(DNA)         (mRNA)                   (phenotype)              (organism)
```

Cognitive layers under `src/core/` (all on one MCP server, [src/core/thinking_os/server.py](src/core/thinking_os/server.py)):
- **thinking_os** = hippocampus (memory + learning + metrics)
- **graph_os** = corpus callosum 
- **board_os** = prefrontal cortex

## Modularity Map — Blast Radius

| Edit | Propagates to | Rebuild |
|---|---|---|
| `src/core/hooks/*.sh` | ALL consumer projects (live symlinks) | none |
| `src/core/thinking_os/**` | ALL projects pointing to this MCP | restart MCP client |
| `src/core/rules/*.md`, `src/core/skills/**` | ALL projects | `cos update` in consumer |
| `src/adapters/<agent>/**` | Only projects with that agent | `cos update` or re-run `install.sh` |
| `src/templates/<stack>/**` | Only projects using that stack | `cos update` + `make manifest-regen` |
| `src/cli/**` | ALL future `cos` invocations (the factory) | `uv tool install --editable .` |

**Derived artifacts — never hand-edit; regenerated from sources above:** `src/core/rules/dimension-registry.md`, `src/core/rules/skill-enforcement.md`, `src/core/scaffold_manifest.json`, `src/adapters/{claude,codex}/*.template.*`, `tests/golden/**`. The `regen-reminder.sh` and `warn-template-drift.sh` hooks catch hand-edits.

## Identity & Principles

coding-os: agent-agnostic cognitive operating system for AI coding agents. Stack: Python + Shell + Markdown. Architecture: Hexagonal (core → adapters → templates).

P1 SSOT-first · P2 Agent-agnostic (never hardcode `.claude/` in core; use `$COS_STATE_DIR`/`$COS_AGENT_DIR`/`$COS_DB_PATH`) · P3 Minimal-context (3-10 files/task) · P4 Diff-first · P5 Dogfood · P6 Log-everything via `make` · P7 No-guessing (log unknowns to `docs/_meta/questions.md`) · P8 Adapter-SDK autonomy (each `src/adapters/<agent>/` self-contained; never import an adapter SDK from `src/core/**`).

## Critical Rules (one-liner index — full text + rationale in [docs/governance/critical-rules.md](docs/governance/critical-rules.md))

| # | Rule (one-liner) | Detail |
|---|---|---|
| 0 | Docs-first — every code Write/Edit traces to `.doc-anchor` (hook BLOCK). | [Rule 0](docs/governance/critical-rules.md#rule-0--docs-first) |
| 1 | Never hardcode `.claude/` in `src/core/`; use `$COS_*` env vars. | [Rule 1](docs/governance/critical-rules.md#rule-1--never-hardcode-claude-in-core) |
| 2 | MCP tool names use `cos_*` prefix. | [Rule 2](docs/governance/critical-rules.md#rule-2--mcp-tool-names-use-cos_-prefix) · [inventory](docs/governance/mcp-tool-inventory.md) |
| 3 | Hooks source `cos-env.sh`. | [Rule 3](docs/governance/critical-rules.md#rule-3--hooks-source-cos-envsh) |
| 4 | Scripts search config chain `$COS_STATE_DIR/domain-config.json` → `infrastructure/scripts/domain-config.json`. | [Rule 4](docs/governance/critical-rules.md#rule-4--scripts-search-config-chain) |
| 5 | `.resolve()` before `.relative_to()` on macOS (/tmp ↔ /private/tmp). | [Rule 5](docs/governance/critical-rules.md#rule-5--path-resolution-resolve-before-relative_to) |
| 6 | Fire-and-forget = `_*_safe()` helper with `except Exception as exc: logger.debug(...)`. | [Rule 6](docs/governance/critical-rules.md#rule-6--fire-and-forget-needs-explicit-exception-handling) |
| 7 | Governance edits require active task marker `docs-update` / `governance`. | [Rule 7](docs/governance/critical-rules.md#rule-7--governance-edits-require-explicit-task-name) |
| 8 | Multi-step verification = Python, never `uv run` + bash heredoc. | [Rule 8](docs/governance/critical-rules.md#rule-8--multi-step-verification--python-never-bash-heredoc-inside--with-uv-run) |
| 9 | Schema migrations append-only — new tables → vN+1, never edit past. | [Rule 9](docs/governance/critical-rules.md#rule-9--schema-migrations-are-append-only) |
| 10 | Regenerate derived artifacts: `make regen-rules` + `manifest-regen` + `regen-adapter-templates`. | [Rule 10](docs/governance/critical-rules.md#rule-10--regenerate-derived-artifacts) |
| 11 | No hardcoded stack/adapter literals in `src/cli/*.py` — data-driven from yaml. | [Rule 11](docs/governance/critical-rules.md#rule-11--no-hardcoded-stackadapter-literals-in-clipy) |
| 12 | Comments by exception, not default. NO docstrings on internal helpers. ONE-line docstring on `@mcp.tool` functions only (FastMCP description). | [Rule 12](docs/governance/critical-rules.md#rule-12--comments-by-exception-not-by-default) |
| 13 | MCP envelope — every `cos_*` returns `ok(data)` / `fail(category, message)` via `@safe_tool`. | [Rule 13](docs/governance/critical-rules.md#rule-13--mcp-tool-response-envelope) · [contract](docs/engineering/mcp-error-envelope.md) |
| 14 | Tasks are pointers — `TASK-NNN-slug.md` never inlines doc content; lint-task warns >1.5k blocks >3k. Axes: swimlane · kind · epic · labels. | [Rule 14](docs/governance/critical-rules.md#rule-14--tasks-are-pointers-not-specs) |
| 15 | COMPLICATED+ tasks call `cos_compose_chain` — 11 semantic roles (researcher · analyst · architect · documenter · implementer · reviewer · debugger · security_auditor · deployer · observer · refactorer). Claude path: [claude-sdk.md](docs/adapters/claude-sdk.md) · deepening checklist: [claude-deepening-checklist.md](docs/adapters/claude-deepening-checklist.md). | [Rule 15](docs/governance/critical-rules.md#rule-15--role-chain-composed-for-complicated-tasks) |
| 16 | Formula dispatch produces typed EvidenceBundle via `cos_supervise_record_output` (or `cos_dispatch_formula_run` when the Claude SDK extra is installed). | [Rule 16](docs/governance/critical-rules.md#rule-16--formula-dispatch-produces-typed-evidencebundle) · [claude-sdk.md §7](docs/adapters/claude-sdk.md) |
| 17 | Situational Paths override role chain when `.situation` set (6 situations). | [Rule 17](docs/governance/critical-rules.md#rule-17--situational-paths-override-role-chain) |
| 18 | Task reconciliation mandatory — check `cos_task_board` first; reuse or create with Outcome/Read First/Acceptance. | [Rule 18](docs/governance/critical-rules.md#rule-18--task-reconciliation-is-mandatory-before-implementation) |
| 19 | Docs are the contract — edit doc before extending code; `enforce-doc-sync.sh` surfaces drift. | [Rule 19](docs/governance/critical-rules.md#rule-19--docs-are-the-contract--never-extend-code-beyond-doc-spec) |
| 20 | Test discipline — matrix command only mid-task; full sweep only pre-merge / cross-cutting / explicit ask. | [Rule 20](docs/governance/critical-rules.md#rule-20--test-discipline-matrix-command-only-never-broad-sweep-mid-task) · [test-discipline.md](src/core/rules/test-discipline.md) |
| 21 | Never `isolation: "worktree"` — Agent tool only for read-only research; write work single-agent. | [Rule 21](docs/governance/critical-rules.md#rule-21--never-use-isolation-worktree-in-this-repo) |
| 22 | Anti-overengineering — reuse-first · no speculation · diff-minimal · rule-of-three abstraction · defer-by-default. Applies to **every artifact** (code, docs, hooks, skills, templates). | [Rule 22](docs/governance/critical-rules.md#rule-22--anti-overengineering) · [rule body](src/core/rules/anti-overengineering.md) |

## Cognition & Tracing

Every `cos_analyze_task`, `cos_compose_chain`, `cos_supervise`, `cos_supervise_record_output`, `cos_backtrack_log` emits a structured event to `.coding-os/<agent>/traces/<session_id>.jsonl` via [src/core/thinking_os/tracing.py](src/core/thinking_os/tracing.py). Inspect:
- `cos cognition trace <session_id>` (pretty timeline) · `cos cognition trace --summary` · `cos cognition trace-replay <session_id>` (CI assertion).


Hook visibility: `cos hooks-log [--follow]`, `cos hooks-list [--agent X] [--category Y] [--phase Z]`. SSOT for hook registration: [src/core/hooks/registry.yaml](src/core/hooks/registry.yaml). Adapter templates are generated from it via `make regen-adapter-templates`.

**Adapter parity is bounded by runtime capability, not adapter design.** Each `src/adapters/<agent>/adapter.yaml::hook_capabilities` declares the `{event, matcher}` pairs that agent's CLI can actually fire. The renderer skips registry entries whose pair isn't in the list — so Codex (Bash-only PreToolUse/PostToolUse, no `Write|Edit` or `Skill` matcher as of 2026-04) emits a smaller template than Claude. This is *correct*, not a gap. When OpenAI adds the missing matchers, update `src/adapters/codex/adapter.yaml` and re-run `make regen-adapter-templates` — no other code changes needed.

## Core Loop — Classify · Orient · Plan · Execute · Verify

**Classify (dry, no reads):** Complexity Gate (Q1 Cynefin × Q2 dimensions, record via `bash src/core/hooks/write-state.sh .coding-os/<agent>/.thinking_os-gate "COMPLICATED 3"`) → reconcile task context (existing TASK-IDs / active board items) → domain route → Read List.
**Orient (targeted reads):** Read List only · `cos_search` for past patterns · grep/glob existing code.
**Plan:** per dimension → current/target/gap/risk → ordered steps. If no matching task exists, create one and fill Outcome/Read First/Acceptance before coding. COMPLICATED+ loads the `thinking_os` skill for Zoom cycles.
**Execute:** smallest correct change [P1, P4]. After code: run verification.
**Verify & Close:** move task to `testing` → run verification (`make verify` or targeted matrix command) → append concise work-log note → `cos task-done TASK-NNN` (Scrumban) or `make task-done` (legacy). Loop on failure: fix → re-run → assert green; never close on assumed pass.

## Verification Matrix

| Changed | Required | Command |
|---|---|---|
| `src/core/thinking_os/*.py` | pytest + MCP self-test | `uv run --extra rag pytest src/core/thinking_os/tests/ -q` and `python src/core/thinking_os/server.py --test` |
| `src/core/thinking_os/database.py` | migration tests | `uv run --extra rag pytest src/core/thinking_os/tests/test_db.py -q` |
| `src/core/graph_os/**` | parity + extractor tests | `uv run --extra graph_os pytest src/core/graph_os/tests/ -q` |
| `src/core/board_os/**` | board_os tests | `uv run --extra rag --with aiohttp --with pytest-asyncio pytest src/core/board_os/tests/ -q` |
| `src/core/hooks/*.sh` or `src/core/scripts/*.sh` | shell syntax | `make verify-hooks` |
| `src/adapters/**` | install test | `uv run pytest tests/test_adapters.py tests/test_adapter_parity.py -q` |
| `src/cli/*.py` | CLI integration | `uv run pytest tests/test_cli.py -q` |
| `src/templates/**/scaffold/**` | scaffold tests | `uv run pytest tests/test_template_scaffold.py -q` |
| `docs/**/*.md` | lint + staleness | `make docs-lint` |

## Tool Routing

**Scrumban (preferred):** `cos board [--web]` · `cos task-show TASK-NNN` · `cos task-create --title … --swimlane … --kind …` · `cos task-start TASK-NNN` · `cos task-move TASK-NNN --to blocked|testing` · `cos task-done TASK-NNN` · `cos daily` · `cos retro` · `cos wip` · `cos task-validate`.
**MCP equivalents:** `cos_task_create`, `cos_task_board`, `cos_task_move`, `cos_task_pick`, `cos_task_daily`, `cos_task_retro`, `cos_task_wip_check`, `cos_work_log_append` (Codex MUST call the last one — no PostToolUse hook).
**Deferred tool schemas (Claude only):** all 79 `cos_*` tools are deferred — schemas are NOT loaded at session start. Call `ToolSearch("select:<tool>")` before the first invocation each session or you get `InputValidationError`. Schema traps (TaskSignals field types, envelope format, UID scheme): [docs/engineering/mcp-schema-traps.md](docs/engineering/mcp-schema-traps.md).
**Meta retrieval (when unsure):** `cos_retrieve(query, hint="auto")` dispatches to memory/docs/tasks or returns a code-grep hint for identifier queries.
**Verify/log:** `make verify` · `make verify-hooks` · `make test-mcp` · `make cos-health` · `cos doctor` · `make log-{latest,write,search}`.
**Web UI (visual exploration):** `cos hub start` boots the singleton FastAPI + React SPA at `http://127.0.0.1:9188`; one hub serves every registered project via `/api/p/<slug>/*`. `cos hub status` reports meta-repo path + symlink health. UI iteration: `make ui-dev` (HMR on :5173) or `make ui-build` (rebuild `dist/`). Full contract + propagation matrix: [docs/engineering/hub-architecture.md](docs/engineering/hub-architecture.md).

**Hub propagation:** `src/core/{hooks,rules,skills,commands}` reach every consumer project via live symlinks. `src/adapters/*/*.template.*` regen + consumer re-render via `cos sync-all`. Dangling symlinks (meta repo moved) → `cos sync-doctor --repair`.

## Four-Layer Retrieval

| Layer | Question | Tools |
|---|---|---|
| Agent Memory | "Have I solved this before?" | `cos_search`, `cos_timeline`, `cos_details`, `cos_learn_suggest` |
| Doc KB | "What does the spec say?" | `cos_doc_search` |
| Tasks + Board | "What's related / next / blocked?" | `cos_task_*` family |
| Meta Router | "I am not sure which layer to use" | `cos_retrieve` |
| Knowledge Graph | "What is connected to what?" | `cos_graph_*` family |

Routing decisions, freshness contract, contracts audit, and the rename workflow: see [docs/engineering/graph_os-queries.md](docs/engineering/graph_os-queries.md) and [docs/engineering/graph-hallucination-cures.md](docs/engineering/graph-hallucination-cures.md).

## Graph-First Discipline (mandatory for `src/core/**`, `src/cli/**`, `src/adapters/**`)

> **Rule:** When the question is structural (callers, blast radius, rename, contracts, trace, similar, communities, context, detect-changes), call the graph **before** Read or grep. One graph envelope (~300 tok) replaces 5–10 file reads (5–50K tok). Hallucination matrix: [docs/engineering/graph-hallucination-cures.md](docs/engineering/graph-hallucination-cures.md).

| Pre-edit move | Tool / hook |
|---|---|
| Load skill | `Skill graph-explorer` (primary) + `Skill clean-code` (secondary). `enforce-skill.sh` BLOCKS edits to `src/core/**/*.py`, `src/cli/**/*.py`, `src/adapters/**/*.py` without `graph-explorer`. |
| Read context before editing | `cos_graph_context(file_or_uid, depth=1)`. `enforce-graph-context.sh` warns (or blocks in strict) without the marker. |
| Before any rename | `cos_graph_rename_plan(uid, new_name)`. `enforce-rename-plan.sh` warns. |
| Before any Read on load-bearing file | `cos_graph_*` should already have run this session. `enforce-graph-first-read.sh` warns (toggle with `COS_ENFORCE_GRAPH_FIRST=strict`). |
| Hot prompt patterns auto-recommend a tool | `nudge-graph-os.sh` (UserPromptSubmit) — 13 bilingual patterns, per-pattern debounced. |

The 16 `cos_graph_*` tools and the hallucinations they cure: see [docs/engineering/graph-hallucination-cures.md](docs/engineering/graph-hallucination-cures.md).

**Polyglot extractor coverage (post-9bee865):** the graph now indexes `.py` `.ts` `.tsx` `.go` `.sh` `.yaml` `.yml` `.md` `.json` `.toml` — JSON and TOML configs (package.json deps, tsconfig paths, mcp.json servers, pyproject deps, Cargo workspaces) are first-class nodes. Shell extractor runs on tree-sitter-bash (no more false-positive function matches inside heredocs/comments). For monorepo-scale repos, `cos graph-reindex --workers N` parallelises across processes. Roadmap + edge-case catalog: [docs/playbooks/polyglot-extractor-roadmap.md](docs/playbooks/polyglot-extractor-roadmap.md) · post-ship audit: [docs/engineering/polyglot-extractor-audit-2026-05-12.md](docs/engineering/polyglot-extractor-audit-2026-05-12.md).

## Key Files

| What | Where |
|---|---|
| MCP server entry | [src/core/thinking_os/server.py](src/core/thinking_os/server.py) |
| DB + migrations | [src/core/thinking_os/database.py](src/core/thinking_os/database.py) |
| MCP tools | [src/core/thinking_os/tools/](src/core/thinking_os/tools/) (memory, metrics, learning, routing, docs, tasks, retrieve, cognition) |
| graph_os | [src/core/graph_os/](src/core/graph_os/) — backends/{kuzu,sqlite}_backend.py |
| board_os | [src/core/board_os/](src/core/board_os/) — config, parser, sync, workflow, mcp_tools |
| Web backbone (S4) | [src/core/web/](src/core/web/) — FastAPI on port 9188, `/api/{graph,board,cognition,search}` + `/api/stream/events` SSE |
| React SPA (S5) | [src/core/web/ui/](src/core/web/ui/) — Vite + React 18 + Sigma.js, served at http://127.0.0.1:9188 |
| Roles (11 semantic) | [src/core/thinking_os/roles/](src/core/thinking_os/roles/) — researcher · analyst · architect · documenter · implementer · reviewer · debugger · security_auditor · deployer · observer · refactorer + presets/registry.yaml |
| Hooks | [src/core/hooks/](src/core/hooks/) (49 scripts) + [registry.yaml](src/core/hooks/registry.yaml) |
| Skills | [src/core/skills/](src/core/skills/) — backend-fundamentals, clean-code, codebase-explorer, frontend-fundamentals, graph-explorer, task-driver, thinking_os |
| CLI | [src/cli/](src/cli/) — main.py + 21 sibling modules (board, brain, graph, doctor, …) |
| Adapters | [src/adapters/claude/](src/adapters/claude/), [src/adapters/codex/](src/adapters/codex/) + [src/adapters/claude/sdk_dispatcher.py](src/adapters/claude/sdk_dispatcher.py) |
| Templates | [src/templates/_base/](src/templates/_base/) + django/nextjs/fastapi/go/go-fiber |


## Persona Enforcement Coverage

Hook enforcement varies by runtime — choose accordingly:

| Runtime | Hooks fire | Use for |
|---|---|---|
| Claude Code | 58/62 ✅ | All protected work (gates + skills + doc-anchor enforce) |
| Cursor (Agent mode) | 59/62 ✅ | All protected work |
| Codex CLI (`codex exec`) | 21/62 ⚠️ | Bash-only — NOT for Write/Edit on `src/core/**` |
| Codex.app (Antigravity GUI) | **0/62** ❌ | DO NOT use for protected work — `.codex/hooks.json` silently ignored upstream |
| Human (direct edit) | 0/62 ❌ | Install `bash src/scripts/install-git-hooks.sh` for git pre-commit coverage |

Audit + reasoning: [docs/engineering/workflow-audit-2026-04-25.md](docs/engineering/workflow-audit-2026-04-25.md). Codex GUI fallback details: [docs/engineering/codex-presence-fallback.md](docs/engineering/codex-presence-fallback.md).

## Stop Conditions

Stop and surface to user when: (a) a `src/core/` change breaks backward compatibility, (b) an adapter change affects another adapter, (c) an MCP tool signature changes without a migration plan.
