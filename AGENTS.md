# AGENTS — Coding OS Development Protocol (META PROJECT)

Root entry point for agents working **ON** coding-os itself. Read first; re-read after context loss. Hard limit: keep this file under 180 lines — overflow goes to [docs/](docs/).

## Nature — Meta-Project (read first, 30s)

**This repo IS the mother.** Its output is projects shaped like itself. A consumer project from `cos init` inherits this same skeleton — same `.coding-os/`, same hooks, same MCP server, same `AGENTS.md` shape — only the **stack** (django, nextjs, go-fiber, …) and **agent** (claude, codex) differ.

Three concentric layers (DNA → mRNA → phenotype):

- **`core/`** — agent-agnostic, stack-agnostic kernel. Hooks, MCP server, rules, skills.
- **`adapters/<agent>/`** — per-agent translation: how the kernel surfaces as `.claude/` or `.codex/`.
- **`templates/<stack>/`** — per-stack overlay: skills + scaffold for one language/framework.

`cos init` composes DNA + mRNA + phenotype → a new project. **This repo is also an instance of what it produces** (P5 Dogfood). Root `CLAUDE.md` is a symlink to `AGENTS.md`; consumer projects only have `AGENTS.md`.

## Mental Model

```
core/  ──►  adapters/<agent>/  ──►  templates/<stack>/  ──►  consumer project
(DNA)         (mRNA)                   (phenotype)              (organism)
```

Cognitive layers under `core/` (all on one MCP server, [core/thinking_os/server.py](core/thinking_os/server.py)):
- **thinking_os** = hippocampus (memory + learning + metrics)
- **graph_os** = corpus callosum (Phase I — Kùzu + SQLite knowledge graph)
- **board_os** = prefrontal cortex (Phase L — Scrumban planner)

## Modularity Map — Blast Radius

| Edit | Propagates to | Rebuild |
|---|---|---|
| `core/hooks/*.sh` | ALL consumer projects (live symlinks) | none |
| `core/thinking_os/**` | ALL projects pointing to this MCP | restart MCP client |
| `core/rules/*.md`, `core/skills/**` | ALL projects | `cos update` in consumer |
| `adapters/<agent>/**` | Only projects with that agent | `cos update` or re-run `install.sh` |
| `templates/<stack>/**` | Only projects using that stack | `cos update` + `make manifest-regen` |
| `cli/**` | ALL future `cos` invocations (the factory) | `uv tool install --editable .` |

**Derived artifacts — never hand-edit; regenerated from sources above:** `core/rules/dimension-registry.md`, `core/rules/skill-enforcement.md`, `core/scaffold_manifest.json`, `adapters/{claude,codex}/*.template.*`, `tests/golden/**`. The `regen-reminder.sh` and `warn-template-drift.sh` hooks catch hand-edits.

## Identity & Principles

coding-os: agent-agnostic cognitive operating system for AI coding agents. Stack: Python + Shell + Markdown. Architecture: Hexagonal (core → adapters → templates).

P1 SSOT-first · P2 Agent-agnostic (never hardcode `.claude/` in core; use `$COS_STATE_DIR`/`$COS_AGENT_DIR`/`$COS_DB_PATH`) · P3 Minimal-context (3-10 files/task) · P4 Diff-first · P5 Dogfood · P6 Log-everything via `make` · P7 No-guessing (log unknowns to `docs/questions.md`) · P8 Adapter-SDK autonomy (each `adapters/<agent>/` self-contained; never import an adapter SDK from `core/**`).

## Critical Rules (full text in [docs/governance/critical-rules.md](docs/governance/critical-rules.md))

0. **Docs-first** — every code Write/Edit must trace to a doc path in `$COS_AGENT_DIR/.doc-anchor`. `enforce-doc-anchor.sh` BLOCKS code writes without an anchor.
1. **Never hardcode `.claude/` in `core/`** — use env vars. State lives in `$COS_AGENT_DIR` (per-agent), shared artifacts in `$COS_STATE_DIR`. Session-id file: `$COS_AGENT_DIR/session-id` (canonical resolution: [core/hooks/cos-env.sh](core/hooks/cos-env.sh)). Agent-prefixed sid string: `ses-{agent}-YYYYMMDD-…`.
2. **MCP tool names use `cos_*` prefix** — see [docs/governance/mcp-tool-inventory.md](docs/governance/mcp-tool-inventory.md) for the full surface (~46 tools across Health · Memory · Metrics · Learning · Routing · Graph · Docs RAG · Tasks · Board · Cognition · Retrieval feedback).
3. **Hooks source `cos-env.sh`** — `source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true`.
4. **Scripts search config chain** — `$COS_STATE_DIR/domain-config.json` → `infrastructure/scripts/domain-config.json`.
5. **Path resolution** — always `.resolve()` before `.relative_to()` on macOS (`/tmp` ↔ `/private/tmp`).
6. **Fire-and-forget needs explicit exception handling** — `except Exception as exc: logger.debug(...)` in a `_*_safe()` helper. `block-bad-patterns.sh` rejects bare `except: pass`.
7. **Governance edits require explicit task name** — edits to `AGENTS.md`, `.coding-os/`, `core/rules/`, `core/hooks/` require active task marker including `docs-update`/`governance` keyword.
8. **Multi-step verification = Python, never bash heredoc inside `$(...)` with `uv run`** — write a `.py` file and `subprocess.run(..., timeout=N)`. See [scripts/verify_phase_c_e2e.py](scripts/verify_phase_c_e2e.py).
9. **Schema migrations append-only** — new tables → migration vN+1, never edit past migrations. `block-migration-conflict.sh` rejects duplicate version in `db.py`.
10. **Regenerate derived artifacts** — change source → `make regen-rules` + `make manifest-regen` + `make regen-adapter-templates`. Hook reminder fires on edit.
11. **No hardcoded stack/adapter literals in `cli/*.py`** — data-driven from `stack.yaml` / `adapter.yaml`. `block-hardcoded-literals.sh` + `tests/test_no_hardcoded_stacks.py` catch quoted `"django"` / `"claude"`.
12. **Function header convention for new Python** — new MCP tools / CLI commands / parsers under `core/thinking_os/**` and `cli/**` start with `PURPOSE / INPUT / OUTPUT / DEPENDENCIES / NOTES` docstring.
13. **MCP tool response envelope** — every `cos_*` tool returns via `ok(data)` / `fail(category, message)` from [core/thinking_os/tools/_shared.py](core/thinking_os/tools/_shared.py). Wrapped in `@safe_tool`. Categories: `transient | validation | permission | not_found | unavailable | internal`. Full contract: [docs/engineering/mcp-error-envelope.md](docs/engineering/mcp-error-envelope.md).
14. **Tasks are pointers, not specs (Phase L)** — `docs/tasks/TASK-NNN-slug.md` MUST NOT inline content already in `docs/**` / `core/rules/**` / `AGENTS.md`. `lint-task.sh` warns >1.5k tokens, blocks >3k. Four orthogonal axes: `swimlane` (domain) · `kind` (8-value enum) · `epic` (free) · `labels` (free; never kind values).
15. **Role chain composed for COMPLICATED+ tasks (Phase N)** — `cos_compose_chain(signals)` written to `.coding-os/<agent>/.roles` + `.role`. Roles ARE the 11 formulas, addressed by semantic id: `researcher · analyst · architect · documenter · implementer · reviewer · debugger · security_auditor · deployer · observer · refactorer`. Routing yaml at [core/thinking_os/roles/](core/thinking_os/roles/), prompts at [core/thinking_os/agents/](core/thinking_os/agents/). Source spec citation `Formula 1..11` retained only in [docs/code-os-core-docs/thinkingos-formulas/formulas-en.md](docs/code-os-core-docs/thinkingos-formulas/formulas-en.md).
16. **Formula dispatch produces typed EvidenceBundle (Phase M)** — every formula records via `cos_supervise_record_output(formula_id, output_json)` matching the formula's `output_schema` Pydantic model.
17. **Situational Paths override role chain when `.situation` set** — six situations: `incident-response`, `onboarding`, `scope-change`, `external-integration`, `design-review`, `existing-project-takeover`.
18. **Task reconciliation is mandatory before implementation** — for each non-trivial user request, first check existing tasks (`cos_task_board` / `cos task-show`). Reuse when matched; otherwise create one, fill Outcome/Read First/Acceptance, then execute statuses `in_progress` → `testing` → `complete` (or `blocked` with explicit blocker).
19. **Docs are the contract — never extend code beyond doc spec.** If the doc says "registration takes username, password, name", do NOT add a `birthdate` field because it "feels needed". Edit the doc first, then the code. Pair: Rule 0 anchors new code TO a doc going IN; `enforce-doc-sync.sh` (PostToolUse Write|Edit|MultiEdit) surfaces docs that drifted going OUT — three signals: (a) symbol removed/renamed + doc still mentions it, (b) signature changed (param-count diff) on a kept symbol, (c) doc mtime older than code AND mentions a current symbol. Collaborates with thinking_os FTS5 index for accurate doc lookup + graph_os `cos_graph_references` for impact context. WARN class — agent must act on the warning, hook can't enforce semantic spec compliance alone.
20. **Test discipline — matrix command only, never broad sweep mid-task.** `pytest tests/ -q` runs 743 integration tests (~6 min). Match changed files → matrix command (15s–90s) per [core/rules/test-discipline.md](core/rules/test-discipline.md). Full sweep is permitted **only** pre-merge/release, cross-cutting refactor touching ≥3 matrix rows, or when user explicitly asks. Single-test debug: `pytest path::TestClass::test_name -v` before re-running the file. Before writing any new test/script/function: P1 SSOT — check `cos_graph_context` / `cos_doc_search` / `grep` first. Reuse, don't duplicate.

## Cognition & Tracing (Phase N.6)

Every `cos_analyze_task`, `cos_compose_chain`, `cos_supervise`, `cos_supervise_record_output`, `cos_backtrack_log` emits a structured event to `.coding-os/<agent>/traces/<session_id>.jsonl` via [core/thinking_os/tracing.py](core/thinking_os/tracing.py). Inspect:
- `cos cognition trace <session_id>` (pretty timeline) · `cos cognition trace --summary` · `cos cognition trace-replay <session_id>` (CI assertion).
- HTML replay: open [docs/cognition-trace-replay.html](docs/cognition-trace-replay.html) and load the JSONL.

Hook visibility: `cos hooks-log [--follow]`, `cos hooks-list [--agent X] [--category Y] [--phase Z]`. SSOT for hook registration: [core/hooks/registry.yaml](core/hooks/registry.yaml). Adapter templates are generated from it via `make regen-adapter-templates`.

**Adapter parity is bounded by runtime capability, not adapter design.** Each `adapters/<agent>/adapter.yaml::hook_capabilities` declares the `{event, matcher}` pairs that agent's CLI can actually fire. The renderer skips registry entries whose pair isn't in the list — so Codex (Bash-only PreToolUse/PostToolUse, no `Write|Edit` or `Skill` matcher as of 2026-04) emits a smaller template than Claude. This is *correct*, not a gap. When OpenAI adds the missing matchers, update `adapters/codex/adapter.yaml` and re-run `make regen-adapter-templates` — no other code changes needed.

## Core Loop — Classify · Orient · Plan · Execute · Verify

**Classify (dry, no reads):** Complexity Gate (Q1 Cynefin × Q2 dimensions, record via `bash core/hooks/write-state.sh .coding-os/<agent>/.thinking_os-gate "COMPLICATED 3"`) → reconcile task context (existing TASK-IDs / active board items) → domain route → Read List.
**Orient (targeted reads):** Read List only · `cos_search` for past patterns · grep/glob existing code.
**Plan:** per dimension → current/target/gap/risk → ordered steps. If no matching task exists, create one and fill Outcome/Read First/Acceptance before coding. COMPLICATED+ loads the `thinking_os` skill for Zoom cycles.
**Execute:** smallest correct change [P1, P4]. After code: run verification.
**Verify & Close:** move task to `testing` → run verification (`make verify` or targeted matrix command) → append concise work-log note → `cos task-done TASK-NNN` (Scrumban) or `make task-done` (legacy).

## Verification Matrix

| Changed | Required | Command |
|---|---|---|
| `core/thinking_os/*.py` | pytest + MCP self-test | `uv run --extra rag pytest core/thinking_os/tests/ -q` and `python core/thinking_os/server.py --test` |
| `core/thinking_os/db.py` | migration tests | `uv run --extra rag pytest core/thinking_os/tests/test_db.py -q` |
| `core/graph_os/**` | parity + extractor tests | `uv run --extra graph_os pytest core/graph_os/tests/ -q` |
| `core/board_os/**` | board_os tests | `uv run --extra rag --with aiohttp --with pytest-asyncio pytest core/board_os/tests/ -q` |
| `core/hooks/*.sh` or `core/scripts/*.sh` | shell syntax | `make verify-hooks` |
| `adapters/**` | install test | `uv run pytest tests/test_adapters.py tests/test_adapter_parity.py -q` |
| `cli/*.py` | CLI integration | `uv run pytest tests/test_cli.py -q` |
| `templates/**/scaffold/**` | scaffold tests | `uv run pytest tests/test_template_scaffold.py -q` |
| `docs/**/*.md` | lint + staleness | `make docs-lint` |

## Tool Routing

**Scrumban (preferred):** `cos board [--web]` · `cos task-show TASK-NNN` · `cos task-create --title … --swimlane … --kind …` · `cos task-start TASK-NNN` · `cos task-move TASK-NNN --to blocked|testing` · `cos task-done TASK-NNN` · `cos daily` · `cos retro` · `cos wip` · `cos task-validate`.
**MCP equivalents:** `cos_task_create`, `cos_task_board`, `cos_task_move`, `cos_task_pick`, `cos_task_daily`, `cos_task_retro`, `cos_task_wip_check`, `cos_work_log_append` (Codex MUST call the last one — no PostToolUse hook).
**Meta retrieval (when unsure):** `cos_retrieve(query, hint="auto")` dispatches to memory/docs/tasks or returns a code-grep hint for identifier queries.
**Verify/log:** `make verify` · `make verify-hooks` · `make test-mcp` · `make cos-health` · `cos doctor` · `make log-{latest,write,search}`.
**Web UI (visual exploration):** `cos hub start` boots the singleton FastAPI + React SPA at `http://127.0.0.1:9188`; one hub serves every registered project via `/api/p/<slug>/*`. `cos hub status` reports meta-repo path + symlink health. UI iteration: `make ui-dev` (HMR on :5173) or `make ui-build` (rebuild `dist/`). Full contract + propagation matrix: [docs/engineering/hub-architecture.md](docs/engineering/hub-architecture.md).

**Hub propagation:** `core/{hooks,rules,skills,commands}` reach every consumer project via live symlinks. `adapters/*/*.template.*` regen + consumer re-render via `cos sync-all`. Dangling symlinks (meta repo moved) → `cos sync-doctor --repair`.

## Four-Layer Retrieval

| Layer | Question | Tools |
|---|---|---|
| Agent Memory | "Have I solved this before?" | `cos_search`, `cos_timeline`, `cos_details`, `cos_learn_suggest` |
| Doc KB (Phase B) | "What does the spec say?" | `cos_doc_search` |
| Tasks + Board (C+L) | "What's related / next / blocked?" | `cos_task_*` family |
| Meta Router (J) | "I am not sure which layer to use" | `cos_retrieve` |
| Knowledge Graph (I) | "What is connected to what?" | `cos_graph_*` family |

Routing decisions, freshness contract, graph rename workflow, contracts audit: see [docs/engineering/retrieval-routing.md](docs/engineering/retrieval-routing.md), [docs/engineering/graph_os-queries.md](docs/engineering/graph_os-queries.md), and [docs/engineering/rename-workflow.md](docs/engineering/rename-workflow.md).

## Key Files

| What | Where |
|---|---|
| MCP server entry | [core/thinking_os/server.py](core/thinking_os/server.py) |
| DB + migrations | [core/thinking_os/db.py](core/thinking_os/db.py) |
| MCP tools | [core/thinking_os/tools/](core/thinking_os/tools/) (memory, metrics, learning, routing, docs, tasks, retrieve, cognition) |
| Phase I graph_os | [core/graph_os/](core/graph_os/) — backends/{kuzu,sqlite}_backend.py |
| Phase L board_os | [core/board_os/](core/board_os/) — config, parser, sync, workflow, mcp_tools |
| Web backbone (S4) | [core/web/](core/web/) — FastAPI on port 9188, `/api/{graph,board,cognition,search}` + `/api/stream/events` SSE |
| React SPA (S5) | [core/web/ui/](core/web/ui/) — Vite + React 18 + Sigma.js, served at http://127.0.0.1:9188 |
| Roles (11 semantic) | [core/thinking_os/roles/](core/thinking_os/roles/) — researcher · analyst · architect · documenter · implementer · reviewer · debugger · security_auditor · deployer · observer · refactorer + presets/registry.yaml |
| Hooks | [core/hooks/](core/hooks/) (49 scripts) + [registry.yaml](core/hooks/registry.yaml) |
| Skills | [core/skills/](core/skills/) — backend-fundamentals, clean-code, codebase-explorer, frontend-fundamentals, graph-explorer, task-driver, thinking_os, worktree-orchestration |
| CLI | [cli/](cli/) — main.py + 21 sibling modules (board, brain, graph, doctor, …) |
| Adapters | [adapters/claude/](adapters/claude/), [adapters/codex/](adapters/codex/) + [adapters/claude/sdk_dispatcher.py](adapters/claude/sdk_dispatcher.py) |
| Templates | [templates/_base/](templates/_base/) + django/nextjs/fastapi/go/go-fiber |

## Phase Status

v0.2.x current. Phases A–N.6 shipped (core, RAG, task store, distribution, hook regime, graph_os, board_os, cognition supervisor, role-based routing, behavioral tracing). Test suite collects ~2,031 tests. Roadmap & open icebox: `cos board` and [docs/development-roadmap.md](docs/development-roadmap.md). Per-phase plans live as `docs/phase-*-plan.md`.

## Stop Conditions

Stop and surface to user when: (a) a `core/` change breaks backward compatibility, (b) an adapter change affects another adapter, (c) an MCP tool signature changes without a migration plan.
